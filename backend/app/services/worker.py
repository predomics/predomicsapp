"""Standalone worker script — runs gpredomicspy in a subprocess so stdout is capturable."""

import json
import re
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


def main():
    param_path = sys.argv[1]
    results_path = sys.argv[2]

    import gpredomicspy

    # Initialize Rust logger so gpredomics progress output goes to stderr
    gpredomicspy.init_logger("info")

    param = gpredomicspy.Param()
    param.load(param_path)

    print("[worker] Starting gpredomics fit...", flush=True)
    print("[worker] Note: if importance computation is enabled, it may take several minutes for large populations.", flush=True)
    experiment = gpredomicspy.fit(param)
    print("[worker] Fit complete.", flush=True)

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

    # Extract jury data directly from gpredomics objects (preferred)
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

    # Print full experiment results (population, importance, voting/jury)
    # PanicException inherits from BaseException, not Exception
    try:
        display_output = experiment.display_results()
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

        if enriched:
            with open(results_path, "w") as f:
                json.dump(results, f, indent=2, default=str)
            print("[worker] Results re-saved with jury/importance data")

    except BaseException as e:
        print(f"[worker] Warning: display_results() failed: {e}")
        # Still try to save if jury was extracted via objects
        if enriched:
            with open(results_path, "w") as f:
                json.dump(results, f, indent=2, default=str)
            print("[worker] Results saved with jury data (display failed)")


if __name__ == "__main__":
    main()
