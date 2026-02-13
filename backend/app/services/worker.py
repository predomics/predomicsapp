"""Standalone worker script — runs gpredomicspy in a subprocess so stdout is capturable."""

import json
import sys


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
    for g in range(n_gens):
        gen_pop = experiment.get_population(g, 0)
        gen_best = gen_pop.best()
        gen_metrics = dict(gen_best.get_metrics())
        generation_tracking.append({
            "generation": g,
            "best_auc": gen_metrics["auc"],
            "best_fit": gen_metrics["fit"],
            "best_k": gen_metrics["k"],
            "population_size": len(gen_pop),
        })

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

    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n[worker] Results saved to {results_path}")


if __name__ == "__main__":
    main()
