"""Standalone worker script — runs gpredomicspy in a subprocess so stdout is capturable."""

import json
import sys


def main():
    param_path = sys.argv[1]
    results_path = sys.argv[2]

    import gpredomicspy

    param = gpredomicspy.Param()
    param.load(param_path)
    experiment = gpredomicspy.fit(param)

    # Extract results
    best_pop = experiment.best_population()
    best = best_pop.best()
    metrics = dict(best.get_metrics())

    results = {
        "fold_count": experiment.fold_count(),
        "generation_count": experiment.generation_count(),
        "execution_time": experiment.execution_time(),
        "feature_names": experiment.feature_names(),
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
    }

    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n[worker] Results saved to {results_path}")


if __name__ == "__main__":
    main()
