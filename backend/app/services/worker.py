"""Standalone worker script — runs gpredomicspy in a subprocess so stdout is capturable."""

import re
import sys

import numpy as np
import pandas as pd
import yaml

from . import matrix_io
from .prediction import (
    DEFAULT_EPSILON,
    UnsupportedModelError,
    compute_auc,
    score_matrix,
    zscore_stats,
)
from .results_io import build_summary, write_json_atomic

# Kept under its historical name for callers/tests.
_compute_auc = compute_auc


def _build_sample_predictions(sample_names, real_classes, votes, predicted_classes):
    """Build per-sample prediction dicts from vote matrix data.

    Consistency matches gpredomics: max_vote_count / total_votes * 100
    (includes all votes: 0, 1, and 2=abstain).
    100% = all experts agree, lower = more disagreement.
    """
    from collections import Counter
    predictions = []
    for i, name in enumerate(sample_names):
        real = int(real_classes[i])
        pred = int(predicted_classes[i]) if i < len(predicted_classes) else 2
        votes_row = [int(v) for v in votes[i]]
        total = len(votes_row)
        if total > 0:
            counts = Counter(votes_row)
            max_count = max(counts.values())
            consistency = max_count / total * 100
        else:
            consistency = 0
        vote_str = "".join(str(v) for v in votes_row)
        predictions.append({
            "name": name,
            "real": real,
            "votes": vote_str,
            "predicted": pred,
            "correct": real == pred,
            "consistency": round(consistency, 1),
        })
    return predictions


def _predict_from_votes(votes, weights=None):
    """Compute predicted classes from vote matrix using weighted majority vote.

    Matches gpredomics Jury.compute_majority_threshold_vote (without threshold_window).
    votes: list of lists — votes[sample][expert], values 0/1/2 (2=abstain)
    weights: optional list of expert weights (same length as experts)
    Returns: list of predicted classes (0, 1, or 2 for tie/rejection)
    """
    predicted = []
    for row in votes:
        weighted_pos = 0.0
        weighted_neg = 0.0
        for j, v in enumerate(row):
            v = int(v)
            if v == 2:
                continue  # abstain
            w = float(weights[j]) if weights and j < len(weights) else 1.0
            if v == 1:
                weighted_pos += w
            elif v == 0:
                weighted_neg += w
        if weighted_pos > weighted_neg:
            predicted.append(1)
        elif weighted_neg > weighted_pos:
            predicted.append(0)
        else:
            predicted.append(2)  # tie → rejection
    return predicted


def _model_epsilon(param_cfg: dict) -> float:
    """Epsilon the engine used for prevalence/log/ratio (``data_type_epsilon``)."""
    general = param_cfg.get("general", {}) or {}
    val = general.get("data_type_epsilon")
    try:
        return float(val) if val is not None else DEFAULT_EPSILON
    except (TypeError, ValueError):
        return DEFAULT_EPSILON


def _train_zscore_stats(experiment, param_cfg: dict) -> dict:
    """Training-set (mean, std) per feature, computed as the engine does.

    The engine standardises with statistics of the samples it trained on
    (after any holdout split), so the same samples are selected by name here.
    Returns {} when the training matrix cannot be read.
    """
    data_cfg = param_cfg.get("data", {}) or {}
    try:
        X = matrix_io.load_matrix(data_cfg["X"], data_cfg.get("features_in_rows", True))
        train_samples = [str(s) for s in experiment.sample_names()]
        X = X.reindex(index=train_samples, columns=[str(f) for f in experiment.feature_names()])
        mean, std = zscore_stats(X.to_numpy(dtype=float, na_value=0.0))
        return {name: (float(m), float(sd)) for name, m, sd in zip(X.columns, mean, std)}
    except Exception as e:  # noqa: BLE001 - optional enrichment, reported in the log
        print(f"[worker] Warning: z-score statistics unavailable: {e}")
        return {}


def _prepare_test_context(experiment, param_path, zstats=None):
    """Load test data once for reuse across generations.

    Returns a context dict with pre-loaded arrays, or None if no test data.
    """
    with open(param_path) as f:
        param_cfg = yaml.safe_load(f)

    data_cfg = param_cfg.get("data", {})
    xtest_path = data_cfg.get("Xtest", "")
    ytest_path = data_cfg.get("ytest", "")

    if not xtest_path or not ytest_path:
        return None

    try:
        features_in_rows = data_cfg.get("features_in_rows", True)
        x_test, y_labels = matrix_io.load_xy(xtest_path, ytest_path, features_in_rows)

        y_arr = pd.to_numeric(y_labels, errors="coerce").to_numpy(dtype=float)
        keep = np.isin(y_arr, (0.0, 1.0))  # the engine ignores unlabelled samples (class 2)
        x_test, y_arr = x_test.loc[keep], y_arr[keep]
        if data_cfg.get("inverse_classes", False):
            y_arr = 1.0 - y_arr
        if len(y_arr) == 0:
            print("[worker] Warning: no labelled test samples (classes 0/1)")
            return None

        feature_names = [str(f) for f in experiment.feature_names()]
        print(f"[worker] Test data loaded: {len(y_arr)} samples, {x_test.shape[1]} features")
        return {
            "y_arr": y_arr,
            # test matrix re-ordered to the training feature order; unseen features are 0
            "x": x_test.reindex(columns=feature_names).to_numpy(dtype=float, na_value=0.0),
            "feature_names": feature_names,
            "epsilon": _model_epsilon(param_cfg),
            "zstats": zstats or {},
        }
    except Exception as e:
        print(f"[worker] Warning: test data loading failed: {e}")
        return None


def _score_individual(ind, ctx):
    """Score one engine Individual on the test context (same maths as the engine)."""
    metrics = dict(ind.get_metrics())
    features = ind.get_features()
    idx = sorted(int(i) for i in features.keys())
    idx = [i for i in idx if i < len(ctx["feature_names"])]
    coefs = np.array([float(features[i]) for i in idx])
    means = stds = None
    if str(metrics.get("data_type")) == "zscore":
        try:
            names = [ctx["feature_names"][i] for i in idx]
            means = np.array([ctx["zstats"][n][0] for n in names])
            stds = np.array([ctx["zstats"][n][1] for n in names])
        except KeyError:
            means = stds = None
    return score_matrix(
        ctx["x"][:, idx], coefs, metrics.get("language"), metrics.get("data_type", "raw"),
        ctx["epsilon"], means, stds,
    )


def _evaluate_one_generation(gen_best, ctx):
    """Test AUC of a generation's best model, or None when it cannot be scored."""
    try:
        return round(compute_auc(ctx["y_arr"], _score_individual(gen_best, ctx)), 6)
    except UnsupportedModelError:
        return None
    except Exception as e:  # noqa: BLE001
        print(f"[worker] Warning: test evaluation failed: {e}")
        return None


def _holdout_auc(experiment):
    """AUC of the final best model on the engine's own held-out samples.

    Returns None when the engine kept no test samples (holdout_ratio 0) or the
    labels are not a 0/1 problem with both classes present.
    """
    try:
        scores = np.asarray(experiment.predict_scores_test(), dtype=float)
        labels = np.asarray(experiment.test_labels(), dtype=float)
    except Exception:  # noqa: BLE001 - older engines or no test split
        return None
    if scores.size == 0 or scores.size != labels.size:
        return None
    if set(np.unique(labels).tolist()) != {0.0, 1.0}:
        return None
    try:
        return round(float(compute_auc(labels, scores)), 6)
    except Exception as e:  # noqa: BLE001
        print(f"[worker] Warning: holdout evaluation failed: {e}")
        return None


def _strip_ansi(text):
    """Remove ANSI escape codes from text."""
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


def _parse_jury_from_display(display_text):
    """Parse jury/voting data from display_results() output.

    Returns a dict with jury metrics, confusion matrices, and expert info,
    or None if no jury data found.
    """
    text = _strip_ansi(display_text)

    # Match: "Majority jury [133 experts] | AUC 1.000/0.760 | accuracy ..."
    jury_match = re.search(
        r'(Majority|Consensus)\s+jury\s+\[(\d+)\s+experts?\]\s*\|'
        r'\s*AUC\s+([\d.]+)/([\d.]+)\s*\|'
        r'\s*accuracy\s+([\d.]+)/([\d.]+)\s*\|'
        r'\s*sensitivity\s+([\d.]+)/([\d.]+)\s*\|'
        r'\s*specificity\s+([\d.]+)/([\d.]+)\s*\|'
        r'\s*rejection rate\s+([\d.]+)/([\d.]+)',
        text
    )
    if not jury_match:
        return None

    jury = {
        "method": jury_match.group(1),
        "expert_count": int(jury_match.group(2)),
        "train": {
            "auc": float(jury_match.group(3)),
            "accuracy": float(jury_match.group(5)),
            "sensitivity": float(jury_match.group(7)),
            "specificity": float(jury_match.group(9)),
            "rejection_rate": float(jury_match.group(11)),
        },
        "test": {
            "auc": float(jury_match.group(4)),
            "accuracy": float(jury_match.group(6)),
            "sensitivity": float(jury_match.group(8)),
            "specificity": float(jury_match.group(10)),
            "rejection_rate": float(jury_match.group(12)),
        },
    }

    # Parse confusion matrices
    for label, key in [("TRAIN", "confusion_train"), ("TEST", "confusion_test")]:
        cm_match = re.search(
            rf'CONFUSION MATRIX \({label}\).*?'
            r'Real 1\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+).*?'
            r'Real 0\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)',
            text, re.DOTALL
        )
        if cm_match:
            jury[key] = {
                "tp": int(cm_match.group(1)),
                "fn": int(cm_match.group(2)),
                "abstain_1": int(cm_match.group(3)),
                "fp": int(cm_match.group(4)),
                "tn": int(cm_match.group(5)),
                "abstain_0": int(cm_match.group(6)),
            }

    # Parse FBM mean stats
    fbm_match = re.search(
        r'FBM mean \(n=(\d+)\)\s*-\s*AUC\s+([\d.]+)/([\d.]+)\s*\|'
        r'\s*accuracy\s+([\d.]+)/([\d.]+)\s*\|'
        r'\s*sensitivity\s+([\d.]+)/([\d.]+)\s*\|'
        r'\s*specificity\s+([\d.]+)/([\d.]+)',
        text
    )
    if fbm_match:
        jury["fbm"] = {
            "count": int(fbm_match.group(1)),
            "train": {
                "auc": float(fbm_match.group(2)),
                "accuracy": float(fbm_match.group(4)),
                "sensitivity": float(fbm_match.group(6)),
                "specificity": float(fbm_match.group(8)),
            },
            "test": {
                "auc": float(fbm_match.group(3)),
                "accuracy": float(fbm_match.group(5)),
                "sensitivity": float(fbm_match.group(7)),
                "specificity": float(fbm_match.group(9)),
            },
        }

    # Parse per-sample predictions (including vote strings for heatmap)
    # Matches: name | real | votes → predicted | ✓/✗/~ | consistency%
    # Rejected samples use ~ and predicted=2, votes may contain 2
    samples = []
    vote_strings = []
    for m in re.finditer(
        r'^\s*(\S+)\s*\|\s*(\d)\s*\|\s*([012]+)\s*.*?→\s*(-?\d+)\s*\|\s*(✓|✗|~)\s*\|\s*([\d.]+)%',
        text, re.MULTILINE
    ):
        vote_str = m.group(3)
        predicted = int(m.group(4))
        result_sym = m.group(5)
        correct = result_sym == "✓"
        samples.append({
            "name": m.group(1),
            "real": int(m.group(2)),
            "votes": vote_str,
            "predicted": predicted,
            "correct": correct,
            "consistency": float(m.group(6)),
        })
        vote_strings.append(vote_str)
    if samples:
        jury["sample_predictions"] = samples
        # Build vote matrix: rows=samples, columns=experts, values=0/1/2
        if vote_strings and all(len(v) == len(vote_strings[0]) for v in vote_strings):
            jury["vote_matrix"] = {
                "sample_names": [s["name"] for s in samples],
                "real_classes": [s["real"] for s in samples],
                "votes": [[int(c) for c in v] for v in vote_strings],
                "n_experts": len(vote_strings[0]),
            }

    return jury


def _parse_importance_from_display(display_text):
    """Parse feature importance from display_results() output.

    Returns a list of {feature, importance, direction} dicts, or None.
    """
    text = _strip_ansi(display_text)

    # Look for importance section — format varies, try common patterns
    # Typical: "Feature importance (MDA, scaled, mean):"
    # Then lines like: "  msp_0069  0.0234  +"
    imp_section = re.search(r'(?:Feature importance|IMPORTANCE).*?\n((?:\s+\S+\s+[\d.e+-]+.*\n)+)', text, re.IGNORECASE)
    if not imp_section:
        return None

    items = []
    for line in imp_section.group(1).strip().split('\n'):
        parts = line.split()
        if len(parts) >= 2:
            try:
                items.append({
                    "feature": parts[0],
                    "importance": float(parts[1]),
                    "direction": parts[2] if len(parts) > 2 else "",
                })
            except ValueError:
                continue
    return items if items else None


def _run_clinical_integration(experiment, param_yaml: dict, clinical_cfg: dict) -> dict:
    """Run clinical data integration after gpredomics fit."""
    clinical_path = clinical_cfg["path"]
    method = clinical_cfg.get("method", "stacking")
    interactions = clinical_cfg.get("interactions", False)
    columns_str = clinical_cfg.get("columns", "")

    # Load clinical data
    clinical_df = pd.read_csv(clinical_path, sep="\t", index_col=0)

    # Filter to requested columns
    if columns_str.strip():
        cols = [c.strip() for c in columns_str.split(",") if c.strip()]
        clinical_df = clinical_df[[c for c in cols if c in clinical_df.columns]]

    # Keep only numeric columns
    clinical_df = clinical_df.select_dtypes(include=[np.number])
    if clinical_df.empty:
        print("[worker] No numeric clinical columns found, skipping integration", flush=True)
        return None

    # Align clinical samples with training data
    train_samples = experiment.sample_names()
    common = [s for s in train_samples if s in clinical_df.index]
    if len(common) < 10:
        print(f"[worker] Only {len(common)} samples overlap between clinical and training data, skipping", flush=True)
        return None

    # Get omics scores from best model
    scores_train = np.array(experiment.predict_scores_train())
    y_train = np.array(experiment.train_labels())

    # Subset to common samples
    train_idx = [train_samples.index(s) for s in common]
    scores_common = scores_train[train_idx]
    y_common = y_train[train_idx]
    clinical_common = clinical_df.loc[common].values

    # Fill NaN with column medians
    col_medians = np.nanmedian(clinical_common, axis=0)
    for j in range(clinical_common.shape[1]):
        mask = np.isnan(clinical_common[:, j])
        clinical_common[mask, j] = col_medians[j]

    from gpredomicspy.clinical import StackingIntegrator, CalibratedCombiner

    result = {"method": method, "clinical_columns": list(clinical_df.columns), "n_samples": len(common)}

    if method in ("stacking", "stacking_l1"):
        integrator = StackingIntegrator(
            method="logistic_l1" if method == "stacking_l1" else "logistic",
            interactions=interactions,
        )
        integrator.fit(scores_common, clinical_common, y_common,
                      clinical_feature_names=list(clinical_df.columns))
        _, train_proba = integrator.predict(scores_common, clinical_common)

        from sklearn.metrics import roc_auc_score
        result["train_auc_combined"] = round(float(roc_auc_score(y_common, train_proba)), 6)
        result["train_auc_omics_only"] = round(float(roc_auc_score(y_common, scores_common)), 6)
        result["feature_importances"] = integrator.feature_importances()
        result["summary"] = integrator.summary()

        # Test data if available
        try:
            scores_test = np.array(experiment.predict_scores_test())
            y_test = np.array(experiment.test_labels())
            test_samples = experiment.sample_names()  # TODO: need test sample names
            # For now, skip test clinical integration (need test sample names from experiment)
        except Exception:
            pass

    elif method == "calibrated":
        # Use first clinical column as the clinical risk score
        combiner = CalibratedCombiner()
        combiner.fit(scores_common, clinical_common[:, 0], y_common)
        _, combined_proba = combiner.predict(scores_common, clinical_common[:, 0])

        from sklearn.metrics import roc_auc_score
        result["train_auc_combined"] = round(float(roc_auc_score(y_common, combined_proba)), 6)
        result["train_auc_omics_only"] = round(float(roc_auc_score(y_common, scores_common)), 6)
        result["summary"] = combiner.summary()

    return result


def _save_results(results_path: str, results: dict) -> None:
    """Write results.json atomically (compact) plus the small summary.json next to it."""
    write_json_atomic(results_path, results)
    try:
        from pathlib import Path
        write_json_atomic(Path(results_path).parent / "summary.json", build_summary(results))
    except OSError as e:
        print(f"[worker] Warning: could not write summary.json: {e}")


def _run_sklearn_worker(param_yaml: dict, results_path: str):
    """Run a sklearn classifier and save results."""
    from .sklearn_runner import run_sklearn

    algo = param_yaml["general"]["algo"]
    algo_params = param_yaml.get(algo, {})
    results = run_sklearn(param_yaml, algo_params)

    results["engine"] = "scikit-learn"
    _save_results(results_path, results)
    print(f"[worker] Results saved to {results_path}", flush=True)


def main():
    import time as _time
    param_path = sys.argv[1]
    results_path = sys.argv[2]

    REGRESSION_FITS = {"spearman", "pearson", "rmse", "mutual_information"}

    # Check if this is a sklearn algorithm
    with open(param_path) as _f:
        _param_yaml = yaml.safe_load(_f)
    algo = _param_yaml.get("general", {}).get("algo", "ga")
    fit_function = _param_yaml.get("general", {}).get("fit", "auc")
    is_regression = fit_function in REGRESSION_FITS

    from .sklearn_runner import is_sklearn_algo
    if is_sklearn_algo(algo):
        _run_sklearn_worker(_param_yaml, results_path)
        return

    import gpredomicspy

    # Initialize Rust logger so gpredomics progress output goes to stderr
    gpredomicspy.init_logger("info")

    t_wall_start = _time.monotonic()
    timing = []  # list of {label, duration_s} dicts for flamegraph

    param = gpredomicspy.Param()
    param.load(param_path)

    print("[worker] Starting gpredomics fit...", flush=True)
    print("[worker] Note: if importance computation is enabled, it may take several minutes for large populations.", flush=True)
    t_fit = _time.monotonic()
    experiment = gpredomicspy.fit(param)
    fit_dur = _time.monotonic() - t_fit
    print(f"[worker] Fit complete. ({fit_dur:.1f}s)", flush=True)
    timing.append({"label": "GA fit", "duration_s": round(fit_dur, 2)})

    # Extract results
    t_extract = _time.monotonic()
    best_pop = experiment.best_population()
    best = best_pop.best()
    metrics = dict(best.get_metrics())
    feature_names = experiment.feature_names()

    # Build full population data for results browsing
    population_data = []
    for i in range(len(best_pop)):
        ind = best_pop.get_individual(i)
        ind_metrics = dict(ind.get_metrics())
        ind_features = ind.get_features()
        named_features = {
            feature_names[int(idx)]: int(coef)
            for idx, coef in ind_features.items()
            if int(idx) < len(feature_names)
        }
        population_data.append({
            "rank": i,
            "metrics": ind_metrics,
            "features": {str(k): int(v) for k, v in ind_features.items()},
            "named_features": named_features,
        })
    extract_dur = _time.monotonic() - t_extract
    print(f"[worker] Population extracted: {len(population_data)} models. ({extract_dur:.1f}s)", flush=True)
    timing.append({"label": "Population extraction", "duration_s": round(extract_dur, 2)})

    # Build per-generation tracking + test evaluation in a SINGLE loop
    t_gen = _time.monotonic()
    generation_tracking = []
    n_gens = experiment.generation_count()

    # Training-set z-score statistics (needed to apply zscore models to other data)
    zstats = _train_zscore_stats(experiment, _param_yaml)

    # Pre-load test data once (if available) for test AUC evaluation.
    # AUC is a classification metric: skipped for regression fits.
    test_ctx = None if is_regression else _prepare_test_context(experiment, param_path, zstats)

    for g in range(n_gens):
        gen_pop = experiment.get_population(g, 0)
        gen_best = gen_pop.best()
        gen_metrics = dict(gen_best.get_metrics())
        entry = {
            "generation": g,
            "best_auc": gen_metrics["auc"],
            "best_fit": gen_metrics["fit"],
            "best_k": gen_metrics["k"],
            "population_size": len(gen_pop),
        }
        # Evaluate on test data if context is available
        if test_ctx is not None:
            test_auc = _evaluate_one_generation(gen_best, test_ctx)
            if test_auc is not None:
                entry["best_auc_test"] = test_auc

        # Sample k×fit pairs for exploration visualization (max 100 per generation)
        pop_size = len(gen_pop)
        sample_size = min(100, pop_size)
        step = max(1, pop_size // sample_size)
        k_fit_sample = []
        fit_values = []
        for idx in range(0, pop_size, step):
            ind = gen_pop.get_individual(idx)
            m = dict(ind.get_metrics())
            k_fit_sample.append([m["k"], round(m["fit"], 4)])
            fit_values.append(m["fit"])
        entry["k_fit_sample"] = k_fit_sample[:100]
        if fit_values:
            entry["fit_mean"] = round(float(np.mean(fit_values)), 4)
            entry["fit_std"] = round(float(np.std(fit_values)), 4)

        generation_tracking.append(entry)

    # No separate test files: the engine still holds out `holdout_ratio` of the
    # training samples and scores the final best model on them. Record that
    # score so the overfitting check and the results show it.
    if test_ctx is None and not is_regression and generation_tracking:
        holdout_auc = _holdout_auc(experiment)
        if holdout_auc is not None:
            generation_tracking[-1]["best_auc_test"] = holdout_auc
            generation_tracking[-1]["test_source"] = "holdout"

    gen_dur = _time.monotonic() - t_gen
    print(f"[worker] Generation tracking: {n_gens} generations. ({gen_dur:.1f}s)", flush=True)
    timing.append({"label": "Generation tracking", "duration_s": round(gen_dur, 2)})

    # Pre-compute stability analysis and store in results
    t_stab = _time.monotonic()
    try:
        from . import stability
        stability_data = stability.compute_stability_analysis(population_data, feature_names)
        stab_dur = _time.monotonic() - t_stab
        print(f"[worker] Stability pre-computed: {stability_data['stats']['n_models']} models. ({stab_dur:.1f}s)", flush=True)
        timing.append({"label": "Stability analysis", "duration_s": round(stab_dur, 2)})
    except Exception as e:
        stab_dur = _time.monotonic() - t_stab
        stability_data = None
        print(f"[worker] Stability computation skipped: {e} ({stab_dur:.1f}s)", flush=True)
        timing.append({"label": "Stability (skipped)", "duration_s": round(stab_dur, 2)})

    results = {
        "fold_count": experiment.fold_count(),
        "generation_count": n_gens,
        "execution_time": experiment.execution_time(),
        "feature_names": feature_names,
        "sample_names": experiment.sample_names(),
        "best_individual": {
            "k": metrics["k"],
            "auc": metrics["auc"],
            "fit": metrics["fit"],
            "accuracy": metrics["accuracy"],
            "sensitivity": metrics["sensitivity"],
            "specificity": metrics["specificity"],
            "threshold": metrics["threshold"],
            "language": metrics["language"],
            "data_type": metrics["data_type"],
            "epoch": metrics["epoch"],
            "features": best.get_features(),
        },
        "population_size": len(best_pop),
        "population": population_data,
        "generation_tracking": generation_tracking,
        "engine": "gpredomics",
        "epsilon": _model_epsilon(_param_yaml),
    }
    # Keep the training statistics of every feature used by a model, so zscore
    # models can be applied to new data later.
    used = {n for ind in population_data for n in ind.get("named_features", {})}
    used.update(
        feature_names[int(i)] for i in best.get_features().keys() if int(i) < len(feature_names)
    )
    if zstats:
        results["zscore_stats"] = {n: list(zstats[n]) for n in sorted(used) if n in zstats}
    if stability_data is not None:
        results["stability"] = stability_data

    # Store regression metadata when using a regression fit function
    if is_regression:
        results["regression"] = {
            "fit_function": fit_function,
            "best_fit": metrics.get("fit"),
        }

    # Clinical integration (if enabled)
    clinical_cfg = _param_yaml.get("clinical", {})
    if clinical_cfg.get("enabled") and clinical_cfg.get("path"):
        t_clin = _time.monotonic()
        try:
            clinical_results = _run_clinical_integration(experiment, _param_yaml, clinical_cfg)
            if clinical_results:
                results["clinical_integration"] = clinical_results
                print(f"[worker] Clinical integration complete: {clinical_results.get('method', '?')}", flush=True)
            clin_dur = _time.monotonic() - t_clin
            timing.append({"label": "Clinical integration", "duration_s": round(clin_dur, 2)})
        except Exception as e:
            clin_dur = _time.monotonic() - t_clin
            print(f"[worker] Clinical integration failed: {e}", flush=True)
            timing.append({"label": "Clinical integration (failed)", "duration_s": round(clin_dur, 2)})

    # Extract ACO pheromone data (if available)
    try:
        if experiment.has_pheromone():
            pheromone_data = experiment.get_pheromone()
            results["pheromone"] = [
                {
                    "feature": dict(p)["feature_name"],
                    "feature_idx": dict(p)["feature_idx"],
                    "tau_positive": round(dict(p)["tau_positive"], 6),
                    "tau_negative": round(dict(p)["tau_negative"], 6),
                    "tau_total": round(dict(p)["tau_total"], 6),
                }
                for p in pheromone_data
            ]
            print(f"[worker] Extracted pheromone data: {len(results['pheromone'])} features", flush=True)
    except Exception as e:
        print(f"[worker] Pheromone extraction skipped: {e}", flush=True)

    # Extract ACO pheromone timeline (if available)
    try:
        if experiment.has_pheromone():
            timeline_data = experiment.get_pheromone_timeline()
            results["pheromone_timeline"] = [
                {
                    "iteration": dict(snap)["iteration"],
                    "entropy": round(dict(snap)["entropy"], 4),
                    "top_features": [
                        {"feature": name, "tau_pos": round(tp, 4), "tau_neg": round(tn, 4)}
                        for name, tp, tn in dict(snap)["top_features"]
                    ],
                }
                for snap in timeline_data
            ]
            print(f"[worker] Extracted pheromone timeline: {len(results['pheromone_timeline'])} snapshots", flush=True)
    except Exception as e:
        print(f"[worker] Pheromone timeline skipped: {e}", flush=True)

    # Compute feature co-occurrence matrix from population
    try:
        if len(population_data) > 1:
            from collections import Counter
            cooccur = Counter()
            for ind in population_data:
                feats = sorted(ind.get("named_features", {}).keys())
                for i in range(len(feats)):
                    for j in range(i + 1, len(feats)):
                        cooccur[(feats[i], feats[j])] += 1
            # Keep top 200 pairs
            top_pairs = cooccur.most_common(200)
            if top_pairs:
                results["feature_cooccurrence"] = [
                    {"feature_a": a, "feature_b": b, "count": c}
                    for (a, b), c in top_pairs
                ]
                print(f"[worker] Feature co-occurrence: {len(top_pairs)} pairs", flush=True)
    except Exception as e:
        print(f"[worker] Co-occurrence skipped: {e}", flush=True)

    # Compute feature discovery timeline from generation tracking
    try:
        if generation_tracking:
            discovery = {}  # feature_name -> first_generation
            for g_entry in generation_tracking:
                g = g_entry["generation"]
                for k_val, _ in g_entry.get("k_fit_sample", []):
                    pass  # k_fit_sample doesn't have feature names
            # Use population data instead: track which features appear in top models
            for rank, ind in enumerate(population_data[:50]):
                for fname in ind.get("named_features", {}).keys():
                    if fname not in discovery:
                        discovery[fname] = {"first_rank": rank}
            if discovery:
                results["feature_discovery"] = [
                    {"feature": f, "first_rank": d["first_rank"]}
                    for f, d in sorted(discovery.items(), key=lambda x: x[1]["first_rank"])
                ]
    except Exception as e:
        print(f"[worker] Feature discovery skipped: {e}", flush=True)

    # Save results first — display_results() may panic in Rust and kill the process
    _save_results(results_path, results)

    print(f"\n[worker] Results saved to {results_path}")

    # Extract jury data directly from gpredomics objects (preferred)
    t_jury = _time.monotonic()
    enriched = False
    try:
        if experiment.has_jury():
            jury_metrics = dict(experiment.get_jury_metrics())
            jury_data = {
                "method": jury_metrics.get("method", "Majority"),
                "expert_count": jury_metrics.get("expert_count", 0),
                "train": {
                    "auc": jury_metrics.get("auc", 0.0),
                    "accuracy": jury_metrics.get("accuracy", 0.0),
                    "sensitivity": jury_metrics.get("sensitivity", 0.0),
                    "specificity": jury_metrics.get("specificity", 0.0),
                    "rejection_rate": jury_metrics.get("rejection_rate", 0.0),
                },
            }

            # Get vote matrix from training data
            try:
                vm = dict(experiment.get_vote_matrix())
                jury_data["vote_matrix"] = {
                    "sample_names": list(vm["sample_names"]),
                    "real_classes": [int(c) for c in vm["real_classes"]],
                    "votes": [[int(v) for v in row] for row in vm["votes"]],
                    "n_experts": int(vm["n_experts"]),
                    "expert_aucs": [float(a) for a in vm["expert_aucs"]],
                }

                # Build per-sample predictions from vote matrix
                sample_predictions = _build_sample_predictions(
                    vm["sample_names"], vm["real_classes"], vm["votes"],
                    jury_metrics.get("predicted_classes", [])
                )
                jury_data["sample_predictions"] = sample_predictions
                print(f"[worker] Extracted vote matrix: {vm['n_experts']} experts × {len(vm['sample_names'])} samples")
            except Exception as e:
                print(f"[worker] Warning: vote matrix extraction failed: {e}")

            # Get test vote matrix if available — build test sample predictions
            try:
                vm_test = dict(experiment.get_vote_matrix_test())
                jury_data["vote_matrix_test"] = {
                    "sample_names": list(vm_test["sample_names"]),
                    "real_classes": [int(c) for c in vm_test["real_classes"]],
                    "votes": [[int(v) for v in row] for row in vm_test["votes"]],
                    "n_experts": int(vm_test["n_experts"]),
                    "expert_aucs": [float(a) for a in vm_test["expert_aucs"]],
                }
                # Build test sample predictions from test vote matrix
                # Use weighted majority vote (same as gpredomics Jury.predict)
                weights = jury_metrics.get("weights", None)
                test_predicted = _predict_from_votes(vm_test["votes"], weights)
                test_preds = _build_sample_predictions(
                    vm_test["sample_names"], vm_test["real_classes"],
                    vm_test["votes"], test_predicted
                )
                jury_data["sample_predictions_test"] = test_preds
                # Use test predictions as primary sample_predictions (errors happen here)
                jury_data["sample_predictions"] = test_preds
                jury_data["test"] = {}
                print(f"[worker] Extracted test vote matrix: {vm_test['n_experts']} experts × {len(vm_test['sample_names'])} samples, {sum(1 for p in test_preds if not p['correct'])} errors")
            except Exception:
                pass  # No test data available

            results["jury"] = jury_data
            enriched = True
            print(f"[worker] Extracted jury data: {jury_data['method']} with {jury_data['expert_count']} experts")
    except Exception as e:
        print(f"[worker] Warning: direct jury extraction failed: {e}")
    jury_dur = _time.monotonic() - t_jury
    timing.append({"label": "Jury extraction", "duration_s": round(jury_dur, 2)})

    # Print full experiment results (population, importance, voting/jury)
    # PanicException inherits from BaseException, not Exception
    try:
        t_display = _time.monotonic()
        display_output = experiment.display_results()
        display_dur = _time.monotonic() - t_display
        print(f"[worker] display_results() completed. ({display_dur:.1f}s)", flush=True)
        timing.append({"label": "display_results()", "duration_s": round(display_dur, 2)})
        print(display_output)

        # If jury wasn't extracted via objects, fall back to text parsing
        if "jury" not in results:
            jury_data = _parse_jury_from_display(display_output)
            if jury_data:
                results["jury"] = jury_data
                enriched = True
                print(f"[worker] Parsed jury data (fallback): {jury_data['method']} with {jury_data['expert_count']} experts")
        else:
            # Enrich with test metrics from display text if not already present
            parsed = _parse_jury_from_display(display_output)
            if parsed and "test" in parsed:
                results["jury"]["test"] = parsed["test"]
            if parsed and "confusion_train" in parsed:
                results["jury"]["confusion_train"] = parsed["confusion_train"]
            if parsed and "confusion_test" in parsed:
                results["jury"]["confusion_test"] = parsed["confusion_test"]
            if parsed and "fbm" in parsed:
                results["jury"]["fbm"] = parsed["fbm"]
            # Use text-parsed sample_predictions as fallback if API didn't produce any
            if parsed and "sample_predictions" in parsed and "sample_predictions" not in results["jury"]:
                results["jury"]["sample_predictions"] = parsed["sample_predictions"]

        importance_data = _parse_importance_from_display(display_output)
        if importance_data:
            results["importance"] = importance_data
            enriched = True
            print(f"[worker] Parsed importance data: {len(importance_data)} features")

    except BaseException as e:
        print(f"[worker] Warning: display_results() failed: {e}")

    # Store timing breakdown in results for flamegraph
    wall_total = round(_time.monotonic() - t_wall_start, 2)
    results["timing"] = {
        "phases": timing,
        "wall_total_s": wall_total,
    }
    # Single final write (jury, importance and timing included).
    _save_results(results_path, results)
    print(f"[worker] Results finalised. Total wall time: {wall_total:.1f}s", flush=True)


if __name__ == "__main__":
    main()
