"""gpredomicspy engine wrapper — bridges FastAPI with the Rust-backed ML engine."""

from __future__ import annotations
import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from ..core.config import settings as app_settings
from ..models.schemas import REGRESSION_FIT_FUNCTIONS

logger = logging.getLogger(__name__)

ADMIN_DEFAULTS_PATH = Path(app_settings.data_dir) / "admin_defaults.json"


def _load_admin_defaults() -> dict:
    """Load admin defaults from disk. Returns flat dict like {"general.language": "bin"}."""
    if ADMIN_DEFAULTS_PATH.exists():
        try:
            return json.loads(ADMIN_DEFAULTS_PATH.read_text())
        except Exception:
            return {}
    return {}


def _apply_admin_defaults(config: dict) -> dict:
    """Apply admin default overrides to a config dict.

    Admin defaults are stored as flat keys like "general.language" -> "bin,ter".
    They override hardcoded defaults but are themselves overridden by user values.
    """
    admin = _load_admin_defaults()
    if not admin:
        return config
    result = {}
    for key, value in config.items():
        if isinstance(value, dict):
            section = dict(value)
            for akey, aval in admin.items():
                parts = akey.split(".", 1)
                if len(parts) == 2 and parts[0] == key:
                    field = parts[1]
                    # Only apply if user hasn't explicitly set a non-default value
                    if field not in section or section[field] is None:
                        section[field] = aval
            result[key] = section
        else:
            result[key] = value
    return result

# Try to import gpredomicspy — it may not be installed yet
try:
    import gpredomicspy
    HAS_ENGINE = True
except ImportError:
    HAS_ENGINE = False
    logger.warning("gpredomicspy not installed — engine calls will use mock mode")


def check_engine() -> bool:
    """Return True if gpredomicspy is available."""
    return HAS_ENGINE


def write_param_yaml(
    config: dict[str, Any],
    x_path: str,
    y_path: str,
    xtest_path: str = "",
    ytest_path: str = "",
    clinical_path: str = "",
    output_dir: str = "/tmp",
) -> str:
    """Write a gpredomics param.yaml from API config dict.

    Merge order: hardcoded defaults ← admin defaults ← user config.
    Returns the path to the generated YAML file.
    """
    # Load admin defaults (flat keys like "general.language" -> "bin")
    admin_defaults = _load_admin_defaults()

    # model_dump() may leave Pydantic Enums — convert to plain values
    def _plain(d):
        return {k: (v.value if hasattr(v, "value") else v) for k, v in d.items()}

    def _admin_section(section_key):
        """Extract admin defaults for a given section."""
        out = {}
        for akey, aval in admin_defaults.items():
            parts = akey.split(".", 1)
            if len(parts) == 2 and parts[0] == section_key:
                out[parts[1]] = aval
        return out

    def _merge(section_key, defaults):
        """Merge: hardcoded defaults ← admin defaults ← user values, stripping None."""
        user = _plain(config.get(section_key, {}))
        merged = {**defaults, **_admin_section(section_key)}
        for k, v in user.items():
            if v is not None:
                merged[k] = v
        return merged

    general = _merge("general", {
        "seed": 42, "algo": "ga", "cv": False, "thread_number": 4, "gpu": False,
        "language": "bin,ter,ratio", "data_type": "raw,prev", "epsilon": 1e-5,
        "fit": "auc", "k_penalty": 0.0001, "fr_penalty": 0.0, "bias_penalty": 0.0,
        "threshold_ci_n_bootstrap": 0, "threshold_ci_penalty": 0.5,
        "threshold_ci_alpha": 0.05, "threshold_ci_frac_bootstrap": 1.0,
        "user_feature_penalties_weight": 1.0, "n_model_to_display": 30,
        "log_level": "info", "keep_trace": True, "display_colorful": True,
        "save_exp": str(Path(output_dir) / "experiment.bin"),
    })

    # When fit is a regression function, disable class-based feature selection
    is_regression = general.get("fit") in REGRESSION_FIT_FUNCTIONS

    data_cfg = config.get("data", {})

    cv = _merge("cv", {
        "outer_folds": 5, "inner_folds": 5, "overfit_penalty": 0.0,
        "resampling_inner_folds_epochs": 0, "fit_on_valid": True,
        "cv_best_models_ci_alpha": 0.05, "cv_fbm_ci_method": "wilson", "stratify_by": "",
    })

    importance = _merge("importance", {
        "compute_importance": False, "n_permutations_mda": 100,
        "scaled_importance": True, "importance_aggregation": "mean",
    })

    voting = _merge("voting", {
        "vote": False, "fbm_ci_alpha": 0.05, "fbm_ci_method": "wilson", "prune_before_voting": False,
        "min_experts": 0, "max_experts": 0,
        "min_perf": 0.5, "min_diversity": 5, "method": "Majority",
        "method_threshold": 0.5, "threshold_windows_pct": 5, "complete_display": False,
    })

    ga = _merge("ga", {
        "population_size": 5000, "max_epochs": 200, "min_epochs": 10,
        "max_age_best_model": 10, "k_min": 1, "k_max": 200,
        "select_elite_pct": 2.0, "select_niche_pct": 0.0, "select_random_pct": 2.0,
        "mutated_children_pct": 80.0, "mutated_features_pct": 20.0,
        "mutation_non_null_chance_pct": 20.0, "forced_diversity_pct": 0.0,
        "forced_diversity_epochs": 10, "random_sampling_pct": 0.0,
        "random_sampling_epochs": 1, "n_epochs_before_global": 0,
    })
    # Rename k_min/k_max to kmin/kmax for gpredomics YAML format
    ga["kmin"] = ga.pop("k_min")
    ga["kmax"] = ga.pop("k_max")

    beam_cfg = _merge("beam", {
        "method": "LimitedExhaustive", "k_start": 1, "k_stop": 100,
        "best_models_criterion": 10.0, "max_nb_of_models": 10000,
    })
    # Rename k_start/k_stop to kmin/kmax for gpredomics YAML format
    beam_out = {
        "method": beam_cfg["method"],
        "kmin": beam_cfg.pop("k_start"),
        "kmax": beam_cfg.pop("k_stop"),
        "best_models_criterion": beam_cfg["best_models_criterion"],
        "max_nb_of_models": beam_cfg["max_nb_of_models"],
    }

    mcmc = config.get("mcmc", {})
    mcmc_out = {
        "n_iter": mcmc.get("n_iter", 1000),
        "n_burn": mcmc.get("n_burn", 500),
        "lambda": mcmc.get("lambda_", mcmc.get("lambda", 0.001)),
        "nmin": mcmc.get("nmin", 10),
    }

    aco = _merge("aco", {
        "n_ants": 100, "max_iterations": 200, "min_iterations": 10,
        "alpha": 1.0, "beta": 2.0, "rho": 0.1,
        "tau_min": 0.01, "tau_max": 1.0, "elite_weight": 2.0,
        "k_min": 1, "k_max": 200, "max_age_best_model": 10,
    })
    aco["kmin"] = aco.pop("k_min")
    aco["kmax"] = aco.pop("k_max")

    gpu = _merge("gpu", {
        "fallback_to_cpu": True, "memory_policy": "Strict",
        "max_total_memory_mb": 256, "max_buffer_size_mb": 128,
    })

    # Sklearn algorithm params (only included if algo is sklearn-based)
    sklearn_algos = {"rf", "svm", "logistic", "xgboost", "lightgbm", "extra_trees", "adaboost", "knn"}
    sklearn_sections = {}
    if general.get("algo") in sklearn_algos:
        algo_key = general["algo"]
        algo_cfg = config.get(algo_key, {})
        if isinstance(algo_cfg, dict):
            sklearn_sections[algo_key] = {k: v for k, v in algo_cfg.items() if v is not None}
        else:
            sklearn_sections[algo_key] = {k: v for k, v in algo_cfg.__dict__.items() if v is not None}

    param = {
        "general": general,
        **sklearn_sections,
        "data": {
            "X": x_path,
            "y": y_path,
            "Xtest": xtest_path,
            "ytest": ytest_path,
            "holdout_ratio": data_cfg.get("holdout_ratio", 0.20),
            "features_in_rows": data_cfg.get("features_in_rows", True),
            "inverse_classes": data_cfg.get("inverse_classes", False),
            "feature_minimal_prevalence_pct": data_cfg.get("feature_minimal_prevalence_pct", 10),
            "feature_selection_method": data_cfg.get("feature_selection_method", "wilcoxon"),
            "feature_maximal_adj_pvalue": data_cfg.get("feature_maximal_adj_pvalue", 0.05),
            "feature_minimal_feature_value": data_cfg.get("feature_minimal_feature_value", 0.0),
            **({"classes": data_cfg["classes"]} if data_cfg.get("classes") else {}),
            **({"feature_maximal_adj_pvalue": 1.0} if is_regression else {}),
        },
        "cv": cv,
        "importance": importance,
        "voting": voting,
        "ga": ga,
        "beam": beam_out,
        "mcmc": mcmc_out,
        "aco": aco,
        "sa": _merge("sa", {"initial_temperature": 1.0, "cooling_rate": 0.999, "min_temperature": 0.001, "max_iterations": 10000, "snapshot_interval": 100, "k_min": 1, "k_max": 50}),
        "lasso": _merge("lasso", {"alpha_min": 0.001, "alpha_max": 1.0, "n_alphas": 100, "l1_ratio": 1.0}),
        "ils": _merge("ils", {"max_iterations": 100, "perturbation_size": 3, "local_search_steps": 50, "max_no_improve": 20, "k_min": 1, "k_max": 50}),
        "gpu": gpu,
    }

    # Add clinical integration config if enabled
    clinical_cfg = config.get("clinical", {})
    if clinical_cfg.get("enabled") and clinical_path:
        param["clinical"] = {
            "enabled": True,
            "path": clinical_path,
            "method": clinical_cfg.get("method", "stacking"),
            "interactions": clinical_cfg.get("interactions", False),
            "columns": clinical_cfg.get("columns", ""),
        }

    yaml_path = Path(output_dir) / "param.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(param, f, default_flow_style=False, sort_keys=False)

    return str(yaml_path)


def run_experiment(param_yaml_path: str) -> dict[str, Any]:
    """Run gpredomics via gpredomicspy and return structured results.

    Returns a dict with experiment summary and best model info.
    """
    if not HAS_ENGINE:
        return _mock_results()

    param = gpredomicspy.Param()
    param.load(param_yaml_path)
    experiment = gpredomicspy.fit(param)

    # Extract results
    best_pop = experiment.best_population()
    best = best_pop.best()
    metrics = dict(best.get_metrics())

    return {
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


def _mock_results() -> dict[str, Any]:
    """Return mock results when gpredomicspy is not available (development mode)."""
    import random

    rng = random.Random(42)
    n_gens = 10

    # Simulate realistic convergence curves for train and test
    generation_tracking = []
    train_auc = 0.55
    test_auc = 0.52
    for g in range(n_gens):
        train_auc += rng.uniform(0.02, 0.05) * (1 - train_auc)
        test_auc += rng.uniform(0.01, 0.04) * (1 - test_auc) + rng.uniform(-0.01, 0.01)
        test_auc = min(test_auc, train_auc - 0.01)
        generation_tracking.append({
            "generation": g,
            "best_auc": round(train_auc, 4),
            "best_auc_test": round(max(0.5, test_auc), 4),
            "best_fit": round(train_auc - 0.001, 4),
            "best_k": rng.choice([2, 3, 3, 3, 4]),
            "population_size": 5000,
        })

    population = []
    for i in range(20):
        auc_val = round(rng.uniform(0.75, 0.90), 4)
        population.append({
            "rank": i,
            "metrics": {
                "auc": auc_val,
                "fit": round(auc_val - 0.001, 4),
                "accuracy": round(rng.uniform(0.70, 0.88), 4),
                "sensitivity": round(rng.uniform(0.70, 0.90), 4),
                "specificity": round(rng.uniform(0.65, 0.88), 4),
                "k": rng.choice([2, 3, 4, 5]),
                "language": rng.choice(["binary", "ternary", "ratio"]),
                "data_type": rng.choice(["raw", "prev"]),
            },
            "features": {},
            "named_features": {f"feature_{rng.randint(0, 49)}": rng.choice([-1, 1]) for _ in range(3)},
        })

    return {
        "fold_count": 1,
        "generation_count": n_gens,
        "execution_time": 5.42,
        "feature_names": [f"feature_{i}" for i in range(50)],
        "sample_names": [f"sample_{i}" for i in range(100)],
        "best_individual": {
            "k": 3,
            "auc": 0.8921,
            "fit": 0.8920,
            "accuracy": 0.8500,
            "sensitivity": 0.8800,
            "specificity": 0.8200,
            "threshold": 0.4500,
            "language": "binary",
            "data_type": "raw",
            "epoch": 8,
            "features": {5: 1, 12: -1, 37: 1},
        },
        "population_size": len(population),
        "population": population,
        "generation_tracking": generation_tracking,
    }
