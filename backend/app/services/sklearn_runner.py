"""SOTA classifier runner using scikit-learn.

Provides Random Forest, SVM, Logistic Regression, XGBoost, LightGBM, and more
as benchmark alternatives to gpredomics. Results are formatted to match the
gpredomics worker output structure for seamless frontend integration.
"""

from __future__ import annotations

import time
import numpy as np
from typing import Any

# Lazy imports — only load what's needed
_CLASSIFIERS = {
    "rf": "Random Forest",
    "svm": "SVM",
    "logistic": "Logistic Regression",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
    "extra_trees": "Extra Trees",
    "adaboost": "AdaBoost",
    "knn": "KNN",
}

SKLEARN_ALGOS = set(_CLASSIFIERS.keys())


def is_sklearn_algo(algo: str) -> bool:
    return algo in SKLEARN_ALGOS


def _load_aligned(
    x_path: str,
    y_path: str,
    features_in_rows: bool = True,
    feature_names: list[str] | None = None,
):
    """Load X and y matched by **sample name** (never by row position).

    Returns (X array samples x features, y int array, feature_names, sample_names).
    Samples present in only one of the two files are dropped, as are samples
    without a label or with the "unknown" class 2. When ``feature_names`` is
    given (the training features), columns are re-ordered to match it and
    features absent from this file are filled with 0.
    """
    import pandas as pd
    from . import matrix_io

    X, y = matrix_io.load_xy(x_path, y_path, features_in_rows)
    n_x, n_y = len(matrix_io.load_matrix(x_path, features_in_rows)), len(matrix_io.load_labels(y_path))
    y = pd.to_numeric(y, errors="coerce")
    keep = y.notna().to_numpy()
    labels = set(y[keep].unique().tolist())
    if labels <= {0, 1, 2}:
        keep = keep & y.isin([0, 1]).to_numpy()
    X, y = X.loc[keep], y.loc[keep]
    if len(X) < n_x or len(X) < n_y:
        print(
            f"[worker] Matched {len(X)} samples by name "
            f"({n_x} in the matrix, {n_y} in the labels).",
            flush=True,
        )
    if len(X) == 0:
        raise ValueError("No labelled samples in common between the matrix and the labels")
    if feature_names is not None:
        missing = [f for f in feature_names if f not in X.columns]
        if missing:
            print(f"[worker] {len(missing)} training features are absent from the test matrix (set to 0).", flush=True)
        X = X.reindex(columns=feature_names)
    values = np.nan_to_num(X.to_numpy(dtype=float), nan=0.0)
    return values, y.to_numpy().astype(int), [str(c) for c in X.columns], [str(i) for i in X.index]


def _build_classifier(algo: str, params: dict):
    """Build a scikit-learn classifier from algo name and params."""
    if algo == "rf":
        from sklearn.ensemble import RandomForestClassifier
        return RandomForestClassifier(
            n_estimators=params.get("n_estimators", 100),
            max_depth=params.get("max_depth") or None,
            min_samples_split=params.get("min_samples_split", 2),
            class_weight="balanced",
            random_state=params.get("seed", 42),
            n_jobs=-1,
        )
    elif algo == "svm":
        from sklearn.svm import SVC
        kernel = params.get("kernel", "linear")
        return SVC(
            kernel=kernel,
            C=params.get("C", 1.0),
            probability=True,
            class_weight="balanced",
            random_state=params.get("seed", 42),
        )
    elif algo == "logistic":
        from sklearn.linear_model import LogisticRegression
        penalty = params.get("penalty", "l1")
        return LogisticRegression(
            penalty=penalty,
            C=params.get("C", 1.0),
            solver="saga" if penalty == "elasticnet" else "liblinear",
            l1_ratio=params.get("l1_ratio", 0.5) if penalty == "elasticnet" else None,
            class_weight="balanced",
            max_iter=params.get("max_iter", 1000),
            random_state=params.get("seed", 42),
        )
    elif algo == "xgboost":
        from xgboost import XGBClassifier
        return XGBClassifier(
            n_estimators=params.get("n_estimators", 100),
            max_depth=params.get("max_depth", 6),
            learning_rate=params.get("learning_rate", 0.1),
            use_label_encoder=False,
            eval_metric="logloss",
            random_state=params.get("seed", 42),
            n_jobs=-1,
        )
    elif algo == "lightgbm":
        from lightgbm import LGBMClassifier
        return LGBMClassifier(
            n_estimators=params.get("n_estimators", 100),
            max_depth=params.get("max_depth", -1),
            learning_rate=params.get("learning_rate", 0.1),
            class_weight="balanced",
            random_state=params.get("seed", 42),
            n_jobs=-1,
            verbose=-1,
        )
    elif algo == "extra_trees":
        from sklearn.ensemble import ExtraTreesClassifier
        return ExtraTreesClassifier(
            n_estimators=params.get("n_estimators", 100),
            max_depth=params.get("max_depth") or None,
            class_weight="balanced",
            random_state=params.get("seed", 42),
            n_jobs=-1,
        )
    elif algo == "adaboost":
        from sklearn.ensemble import AdaBoostClassifier
        return AdaBoostClassifier(
            n_estimators=params.get("n_estimators", 50),
            learning_rate=params.get("learning_rate", 1.0),
            random_state=params.get("seed", 42),
        )
    elif algo == "knn":
        from sklearn.neighbors import KNeighborsClassifier
        return KNeighborsClassifier(
            n_neighbors=params.get("n_neighbors", 5),
            weights=params.get("weights", "uniform"),
            n_jobs=-1,
        )
    else:
        raise ValueError(f"Unknown sklearn algorithm: {algo}")


def _compute_metrics(y_true, y_pred, y_proba=None):
    """Compute classification metrics matching gpredomics output."""
    from sklearn.metrics import (
        accuracy_score, roc_auc_score, f1_score,
        matthews_corrcoef, precision_score, recall_score,
        confusion_matrix,
    )

    acc = accuracy_score(y_true, y_pred)
    sens = recall_score(y_true, y_pred, pos_label=1, zero_division=0)
    spec = recall_score(y_true, y_pred, pos_label=0, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    mcc = matthews_corrcoef(y_true, y_pred)
    ppv = precision_score(y_true, y_pred, pos_label=1, zero_division=0)
    npv = precision_score(y_true, y_pred, pos_label=0, zero_division=0)
    g_mean = float(np.sqrt(sens * spec))

    auc = 0.5
    if y_proba is not None and len(np.unique(y_true)) > 1:
        try:
            auc = roc_auc_score(y_true, y_proba)
        except ValueError:
            pass

    return {
        "auc": round(auc, 6),
        "accuracy": round(acc, 6),
        "sensitivity": round(sens, 6),
        "specificity": round(spec, 6),
        "f1": round(f1, 6),
        "mcc": round(mcc, 6),
        "ppv": round(ppv, 6),
        "npv": round(npv, 6),
        "g_mean": round(g_mean, 6),
    }


def _feature_importance(clf, algo: str, feature_names: list[str], X, y):
    """Extract feature importance from a trained classifier."""
    importances = None

    # Tree-based models have built-in feature importance
    if hasattr(clf, "feature_importances_"):
        importances = clf.feature_importances_
    # Linear models have coefficients
    elif hasattr(clf, "coef_"):
        importances = np.abs(clf.coef_).ravel()
    # Fallback: permutation importance
    else:
        try:
            from sklearn.inspection import permutation_importance
            result = permutation_importance(clf, X, y, n_repeats=10, random_state=42, n_jobs=-1)
            importances = result.importances_mean
        except Exception:
            return None

    if importances is None:
        return None

    # Sort by importance descending
    indices = np.argsort(importances)[::-1]
    items = []
    for idx in indices:
        if importances[idx] > 0:
            items.append({
                "feature": feature_names[idx] if idx < len(feature_names) else str(idx),
                "importance": round(float(importances[idx]), 6),
                "direction": "",
            })
    return items


def run_sklearn(param_yaml: dict, algo_params: dict) -> dict[str, Any]:
    """Run a scikit-learn classifier and return results in gpredomics-compatible format.

    Args:
        param_yaml: Parsed param.yaml dict (contains data paths, general settings)
        algo_params: Algorithm-specific parameters (n_estimators, C, etc.)

    Returns:
        Results dict matching the gpredomics worker output structure.
    """
    t_start = time.monotonic()
    timing = []

    algo = param_yaml["general"]["algo"]
    seed = param_yaml["general"].get("seed", 42)
    algo_params["seed"] = seed
    features_in_rows = param_yaml["data"].get("features_in_rows", True)

    print(f"[worker] Running {_CLASSIFIERS.get(algo, algo)}...", flush=True)

    # Load data
    t_load = time.monotonic()
    X_train, y_train, feature_names, sample_names_train = _load_aligned(
        param_yaml["data"]["X"], param_yaml["data"]["y"], features_in_rows,
    )

    X_test, y_test, sample_names_test = None, None, None
    has_test = bool(param_yaml["data"].get("Xtest")) and bool(param_yaml["data"].get("ytest"))
    if has_test:
        X_test, y_test, _, sample_names_test = _load_aligned(
            param_yaml["data"]["Xtest"], param_yaml["data"]["ytest"], features_in_rows,
            feature_names=feature_names,
        )

    load_dur = time.monotonic() - t_load
    print(f"[worker] Data loaded: {X_train.shape[0]} train samples, {X_train.shape[1]} features. ({load_dur:.1f}s)", flush=True)
    timing.append({"label": "Data loading", "duration_s": round(load_dur, 2)})

    # Handle CV or holdout
    use_cv = param_yaml["general"].get("cv", False)

    if use_cv:
        return _run_with_cv(algo, algo_params, X_train, y_train, X_test, y_test,
                           feature_names, sample_names_train, sample_names_test,
                           param_yaml, timing, t_start)

    # Simple train/test or holdout
    if X_test is None:
        # Apply holdout split
        holdout_ratio = param_yaml["data"].get("holdout_ratio", 0.2)
        if holdout_ratio > 0:
            from sklearn.model_selection import train_test_split
            X_train, X_test, y_train, y_test, sample_names_train, sample_names_test = train_test_split(
                X_train, y_train, sample_names_train, test_size=holdout_ratio,
                random_state=seed, stratify=y_train
            )
            print(f"[worker] Holdout split: {len(y_train)} train, {len(y_test)} test", flush=True)

    # Train
    t_fit = time.monotonic()
    clf = _build_classifier(algo, algo_params)
    clf.fit(X_train, y_train)
    fit_dur = time.monotonic() - t_fit
    print(f"[worker] {_CLASSIFIERS.get(algo, algo)} trained. ({fit_dur:.1f}s)", flush=True)
    timing.append({"label": f"{algo} fit", "duration_s": round(fit_dur, 2)})

    # Train metrics
    y_train_pred = clf.predict(X_train)
    y_train_proba = clf.predict_proba(X_train)[:, 1] if hasattr(clf, "predict_proba") else None
    train_metrics = _compute_metrics(y_train, y_train_pred, y_train_proba)

    # Test metrics
    test_metrics = None
    if X_test is not None:
        y_test_pred = clf.predict(X_test)
        y_test_proba = clf.predict_proba(X_test)[:, 1] if hasattr(clf, "predict_proba") else None
        test_metrics = _compute_metrics(y_test, y_test_pred, y_test_proba)
        print(f"[worker] Test AUC: {test_metrics['auc']:.4f}", flush=True)

    # Feature importance
    t_imp = time.monotonic()
    importance = _feature_importance(clf, algo, feature_names, X_train, y_train)
    imp_dur = time.monotonic() - t_imp
    if importance:
        timing.append({"label": "Feature importance", "duration_s": round(imp_dur, 2)})
        print(f"[worker] Feature importance computed: {len(importance)} features. ({imp_dur:.1f}s)", flush=True)

    # Build top features dict (for best_individual compatibility)
    top_features = {}
    if importance:
        for item in importance[:20]:  # top 20
            idx = feature_names.index(item["feature"]) if item["feature"] in feature_names else -1
            if idx >= 0:
                top_features[str(idx)] = 1

    wall_total = round(time.monotonic() - t_start, 2)
    timing.append({"label": "Total", "duration_s": wall_total})

    results = {
        "fold_count": 1,
        "generation_count": 1,
        "execution_time": wall_total,
        "feature_names": feature_names,
        "sample_names": list(sample_names_train),
        "algo": algo,
        "algo_label": _CLASSIFIERS.get(algo, algo),
        "best_individual": {
            "k": len(top_features),
            "auc": train_metrics["auc"],
            "fit": train_metrics["auc"],
            "accuracy": train_metrics["accuracy"],
            "sensitivity": train_metrics["sensitivity"],
            "specificity": train_metrics["specificity"],
            "threshold": 0.5,
            "language": algo,
            "data_type": "raw",
            "epoch": 0,
            "features": top_features,
        },
        "train_metrics": train_metrics,
        "population_size": 1,
        "population": [{
            "rank": 0,
            "metrics": {
                "auc": train_metrics["auc"],
                "fit": train_metrics["auc"],
                "accuracy": train_metrics["accuracy"],
                "sensitivity": train_metrics["sensitivity"],
                "specificity": train_metrics["specificity"],
                "threshold": 0.5,
                "k": len(top_features),
                "language": algo,
                "data_type": "raw",
                "epoch": 0,
            },
            "features": top_features,
            "named_features": {
                feature_names[int(k)]: int(v) for k, v in top_features.items()
                if int(k) < len(feature_names)
            },
        }],
        "generation_tracking": [{
            "generation": 0,
            "best_auc": train_metrics["auc"],
            "best_fit": train_metrics["auc"],
            "best_k": len(top_features),
            "population_size": 1,
        }],
        "timing": {
            "phases": timing,
            "wall_total_s": wall_total,
        },
    }

    if test_metrics:
        results["test_metrics"] = test_metrics
        results["generation_tracking"][0]["best_auc_test"] = test_metrics["auc"]

    if importance:
        results["importance"] = importance

    return results


def _run_with_cv(algo, algo_params, X, y, X_test, y_test,
                 feature_names, sample_names_train, sample_names_test,
                 param_yaml, timing, t_start):
    """Run classifier with cross-validation."""
    from sklearn.model_selection import StratifiedKFold
    from sklearn.metrics import roc_auc_score

    n_folds = param_yaml.get("cv", {}).get("outer_folds", 5)
    seed = algo_params.get("seed", 42)

    print(f"[worker] Running {n_folds}-fold CV...", flush=True)

    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)
    fold_metrics = []
    all_oof_proba = np.zeros(len(y))
    all_oof_pred = np.zeros(len(y), dtype=int)
    importances_list = []

    for fold_idx, (train_idx, val_idx) in enumerate(skf.split(X, y)):
        t_fold = time.monotonic()
        X_tr, X_val = X[train_idx], X[val_idx]
        y_tr, y_val = y[train_idx], y[val_idx]

        clf = _build_classifier(algo, algo_params)
        clf.fit(X_tr, y_tr)

        y_val_pred = clf.predict(X_val)
        y_val_proba = clf.predict_proba(X_val)[:, 1] if hasattr(clf, "predict_proba") else None

        all_oof_pred[val_idx] = y_val_pred
        if y_val_proba is not None:
            all_oof_proba[val_idx] = y_val_proba

        fold_m = _compute_metrics(y_val, y_val_pred, y_val_proba)
        fold_metrics.append(fold_m)

        imp = _feature_importance(clf, algo, feature_names, X_tr, y_tr)
        if imp:
            importances_list.append(imp)

        fold_dur = time.monotonic() - t_fold
        print(f"[worker] Fold {fold_idx+1}/{n_folds}: AUC={fold_m['auc']:.4f} ({fold_dur:.1f}s)", flush=True)

    # Aggregate CV metrics
    cv_metrics = {}
    for key in fold_metrics[0]:
        values = [fm[key] for fm in fold_metrics]
        cv_metrics[key] = round(float(np.mean(values)), 6)
        cv_metrics[f"{key}_std"] = round(float(np.std(values)), 6)

    # Overall OOF AUC
    try:
        oof_auc = roc_auc_score(y, all_oof_proba)
    except ValueError:
        oof_auc = cv_metrics["auc"]

    cv_dur = time.monotonic() - t_start
    timing.append({"label": f"{n_folds}-fold CV", "duration_s": round(cv_dur, 2)})
    print(f"[worker] CV complete. Mean AUC: {cv_metrics['auc']:.4f} ± {cv_metrics['auc_std']:.4f}, OOF AUC: {oof_auc:.4f}", flush=True)

    # Aggregate importance across folds
    importance = None
    if importances_list:
        imp_dict = {}
        for imp_list in importances_list:
            for item in imp_list:
                name = item["feature"]
                if name not in imp_dict:
                    imp_dict[name] = []
                imp_dict[name].append(item["importance"])
        importance = sorted(
            [{"feature": k, "importance": round(float(np.mean(v)), 6), "direction": ""}
             for k, v in imp_dict.items()],
            key=lambda x: x["importance"], reverse=True
        )

    # Train final model on all data for test evaluation
    test_metrics = None
    if X_test is not None:
        clf_final = _build_classifier(algo, algo_params)
        clf_final.fit(X, y)
        y_test_pred = clf_final.predict(X_test)
        y_test_proba = clf_final.predict_proba(X_test)[:, 1] if hasattr(clf_final, "predict_proba") else None
        test_metrics = _compute_metrics(y_test, y_test_pred, y_test_proba)
        print(f"[worker] Test AUC (final model): {test_metrics['auc']:.4f}", flush=True)

    top_features = {}
    if importance:
        for item in importance[:20]:
            idx = feature_names.index(item["feature"]) if item["feature"] in feature_names else -1
            if idx >= 0:
                top_features[str(idx)] = 1

    wall_total = round(time.monotonic() - t_start, 2)

    results = {
        "fold_count": n_folds,
        "generation_count": 1,
        "execution_time": wall_total,
        "feature_names": feature_names,
        "sample_names": list(sample_names_train),
        "algo": algo,
        "algo_label": _CLASSIFIERS.get(algo, algo),
        "best_individual": {
            "k": len(top_features),
            "auc": cv_metrics["auc"],
            "fit": cv_metrics["auc"],
            "accuracy": cv_metrics["accuracy"],
            "sensitivity": cv_metrics["sensitivity"],
            "specificity": cv_metrics["specificity"],
            "threshold": 0.5,
            "language": algo,
            "data_type": "raw",
            "epoch": 0,
            "features": top_features,
        },
        "train_metrics": cv_metrics,
        "cv_fold_metrics": fold_metrics,
        "oof_auc": round(oof_auc, 6),
        "population_size": 1,
        "population": [{
            "rank": 0,
            "metrics": {
                "auc": cv_metrics["auc"],
                "fit": cv_metrics["auc"],
                "accuracy": cv_metrics["accuracy"],
                "sensitivity": cv_metrics["sensitivity"],
                "specificity": cv_metrics["specificity"],
                "threshold": 0.5,
                "k": len(top_features),
                "language": algo,
                "data_type": "raw",
                "epoch": 0,
            },
            "features": top_features,
            "named_features": {
                feature_names[int(k)]: int(v) for k, v in top_features.items()
                if int(k) < len(feature_names)
            },
        }],
        "generation_tracking": [{
            "generation": 0,
            "best_auc": cv_metrics["auc"],
            "best_fit": cv_metrics["auc"],
            "best_k": len(top_features),
            "population_size": 1,
        }],
        "timing": {
            "phases": timing,
            "wall_total_s": wall_total,
        },
    }

    if test_metrics:
        results["test_metrics"] = test_metrics
        results["generation_tracking"][0]["best_auc_test"] = test_metrics["auc"]

    if importance:
        results["importance"] = importance

    return results
