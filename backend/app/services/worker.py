"""Standalone worker script — runs gpredomicspy in a subprocess so stdout is capturable."""

import json
import sys

import numpy as np
import pandas as pd
import yaml


def _compute_auc(y_true, scores):
    """Compute AUC using the trapezoidal rule (no sklearn dependency)."""
    order = np.argsort(-scores)
    y_sorted = y_true[order]
    n_pos = int(np.sum(y_sorted == 1))
    n_neg = len(y_sorted) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    tp = fp = 0
    auc = 0.0
    tpr_prev = fpr_prev = 0.0
    for label in y_sorted:
        if label == 1:
            tp += 1
        else:
            fp += 1
        tpr = tp / n_pos
        fpr = fp / n_neg
        auc += (fpr - fpr_prev) * (tpr + tpr_prev) / 2
        tpr_prev, fpr_prev = tpr, fpr
    return float(auc)


def _evaluate_test_per_generation(experiment, param_path):
    """Evaluate each generation's best model on test data.

    Returns a dict mapping generation index to test AUC, or empty dict if
    no test data is available.
    """
    with open(param_path) as f:
        param_cfg = yaml.safe_load(f)

    data_cfg = param_cfg.get("data", {})
    xtest_path = data_cfg.get("Xtest", "")
    ytest_path = data_cfg.get("ytest", "")

    if not xtest_path or not ytest_path:
        return {}

    try:
        features_in_rows = data_cfg.get("features_in_rows", True)

        # Load test data
        x_test = pd.read_csv(xtest_path, sep="\t", index_col=0)
        y_test = pd.read_csv(ytest_path, sep="\t", index_col=0)

        # Transpose so rows = samples, columns = features
        if features_in_rows:
            x_test = x_test.T

        y_labels = y_test.iloc[:, 0]

        # Align samples present in both X and y
        common = x_test.index.intersection(y_labels.index)
        if len(common) == 0:
            print("[worker] Warning: no common samples between X_test and y_test")
            return {}

        x_test = x_test.loc[common]
        y_arr = y_labels.loc[common].values.astype(float)
        x_raw = x_test.values.astype(float)

        # Pre-compute prevalence-normalised version (row sums = sample totals)
        row_sums = x_raw.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1.0
        x_prev = x_raw / row_sums

        # Map feature name -> column index in x_test
        feature_names = experiment.feature_names()
        test_col_idx = {name: i for i, name in enumerate(x_test.columns)}

        n_gens = experiment.generation_count()
        test_aucs = {}

        for g in range(n_gens):
            gen_pop = experiment.get_population(g, 0)
            gen_best = gen_pop.best()
            gen_metrics = dict(gen_best.get_metrics())
            features = gen_best.get_features()  # {feature_idx: coef}
            data_type = gen_metrics.get("data_type", "raw")

            x_eval = x_prev if data_type == "prevalence" else x_raw

            scores = np.zeros(len(x_eval))
            for feat_idx, coef in features.items():
                idx = int(feat_idx)
                if idx >= len(feature_names):
                    continue
                feat_name = feature_names[idx]
                if feat_name in test_col_idx:
                    scores += x_eval[:, test_col_idx[feat_name]] * float(coef)

            test_aucs[g] = round(_compute_auc(y_arr, scores), 6)

        print(f"[worker] Test AUC evaluated on {len(common)} samples across {n_gens} generations")
        return test_aucs

    except Exception as e:
        print(f"[worker] Warning: test evaluation failed: {e}")
        return {}


def main():
    param_path = sys.argv[1]
    results_path = sys.argv[2]

    import gpredomicspy

    # Initialize Rust logger so gpredomics progress output goes to stderr
    gpredomicspy.init_logger("info")

    param = gpredomicspy.Param()
    param.load(param_path)
    experiment = gpredomicspy.fit(param)

    # Extract results
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

    # Build per-generation tracking for convergence chart
    generation_tracking = []
    n_gens = experiment.generation_count()

    # Evaluate each generation's best model on test data (if available)
    print("[worker] Evaluating models on test data...")
    test_aucs = _evaluate_test_per_generation(experiment, param_path)

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
        if g in test_aucs:
            entry["best_auc_test"] = test_aucs[g]
        generation_tracking.append(entry)

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
    }

    # Save results first — display_results() may panic in Rust and kill the process
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n[worker] Results saved to {results_path}")

    # Print full experiment results (population, importance, voting/jury)
    # PanicException inherits from BaseException, not Exception
    try:
        display_output = experiment.display_results()
        print(display_output)
    except BaseException as e:
        print(f"[worker] Warning: display_results() failed: {e}")


if __name__ == "__main__":
    main()
