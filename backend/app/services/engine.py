"""gpredomicspy engine wrapper — bridges FastAPI with the Rust-backed ML engine."""

from __future__ import annotations
import json
import logging
import math
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

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


# ---------------------------------------------------------------------------
# Effective settings (hardcoded defaults <- admin defaults <- user config)
# ---------------------------------------------------------------------------

_GENERAL_DEFAULTS = {"algo": "ga", "language": "bin,ter,ratio", "data_type": "raw,prev,zscore"}
_GA_SELECTION_DEFAULTS = {
    "population_size": 5000, "select_elite_pct": 2.0, "select_niche_pct": 0.0,
    "select_random_pct": 2.0, "forced_diversity_pct": 0.0,
}


def _effective(config: dict, section: str, defaults: dict) -> dict:
    """Values the engine will really get for ``section`` (same merge as write_param_yaml)."""
    merged = dict(defaults)
    for key, value in _load_admin_defaults().items():
        parts = key.split(".", 1)
        if len(parts) == 2 and parts[0] == section and parts[1] in defaults:
            merged[parts[1]] = value
    for key, value in ((config or {}).get(section) or {}).items():
        if key in defaults and value is not None:
            merged[key] = value.value if hasattr(value, "value") else value
    return merged


def _csv(value) -> list[str]:
    return [v.strip().lower() for v in str(value or "").split(",") if v.strip()]


# ---------------------------------------------------------------------------
# Genetic algorithm: enough parents to breed
# ---------------------------------------------------------------------------

# gpredomics removes duplicate models every generation, so the population it
# selects parents from is usually a little smaller than population_size. The
# check below assumes up to this share can be lost.
GA_DUPLICATE_MARGIN = 0.20


def ga_guaranteed_parents(population: int, elite_pct: float, niche_pct: float,
                          random_pct: float, n_types: int) -> int:
    """Parents gpredomics is certain to select from ``population`` models.

    Mirrors ``select_parents`` in gpredomics ``src/ga.rs`` — every count is
    truncated to an integer, and the niche and random shares are split evenly
    between the (language, data type) combinations before truncation::

        elite  = floor(population * elite_pct / 100)
        niche  = n_types * floor(population * niche_pct  / 100 / n_types)
        random = n_types * floor(population * random_pct / 100 / n_types)

    ``cross_over`` then draws two distinct parents and panics ("Vec must have
    exactly 2 elements") when fewer than two were selected.
    """
    n_types = max(1, int(n_types))
    elite = int(population * elite_pct / 100.0)
    niche = n_types * int(population * niche_pct / 100.0 / n_types) if niche_pct > 0 else 0
    rand = n_types * int(population * random_pct / 100.0 / n_types)
    return elite + niche + rand


def check_ga_selection(config: dict) -> None:
    """Raise ValueError if a GA run would select fewer than two parents.

    Does nothing for other algorithms. The message says which values to raise.
    Can be switched off with PREDOMICS_GA_PARENT_GUARD=false once the installed
    engine tops up the parent pool itself.
    """
    guard = getattr(app_settings, "ga_parent_guard", None)
    if guard is None:
        guard = os.environ.get("PREDOMICS_GA_PARENT_GUARD", "true")
    if str(guard).strip().lower() in ("0", "false", "no", "off"):
        return
    general = _effective(config, "general", _GENERAL_DEFAULTS)
    if str(general["algo"]).lower() != "ga":
        return
    ga = _effective(config, "ga", _GA_SELECTION_DEFAULTS)
    try:
        population = int(ga["population_size"])
        elite, niche, rand = (float(ga[k]) for k in ("select_elite_pct", "select_niche_pct", "select_random_pct"))
    except (TypeError, ValueError):
        return  # not numbers: schema validation reports that
    n_types = max(1, len(_csv(general["language"])) * len(_csv(general["data_type"])))

    def parents(pop: int, elite_pct: float = elite) -> int:
        usable = int(pop * (1.0 - GA_DUPLICATE_MARGIN))
        return ga_guaranteed_parents(usable, elite_pct, niche, rand, n_types)

    have = parents(population)
    if have >= 2:
        return

    needed_population = population
    if elite > 0 or rand > 0 or niche > 0:
        while parents(needed_population) < 2 and needed_population < 10_000_000:
            needed_population += max(1, needed_population // 50)
        while needed_population > population + 1 and parents(needed_population - 1) >= 2:
            needed_population -= 1
    usable = max(1, int(population * (1.0 - GA_DUPLICATE_MARGIN)))
    needed_elite = math.ceil(2 * 100.0 / usable * 100) / 100
    options = []
    if parents(needed_population) >= 2:
        options.append(f"population_size to at least {needed_population}")
    if needed_elite <= 100:
        options.append(f"select_elite_pct to at least {needed_elite:g}")
    raise ValueError(
        f"The genetic algorithm needs at least 2 parents per generation, but population_size={population} "
        f"with select_elite_pct={elite:g}, select_random_pct={rand:g} and select_niche_pct={niche:g} "
        f"over {n_types} language/data-type combination(s) guarantees only {have}. "
        f"Raise {' or '.join(options) if options else 'the selection percentages'}."
    )


# ---------------------------------------------------------------------------
# Engine capabilities (what the installed gpredomicspy can actually do)
# ---------------------------------------------------------------------------

KNOWN_DATA_TYPES = ("raw", "prev", "log", "zscore")
KNOWN_LANGUAGES = ("bin", "ter", "ratio", "pow2")
_PROBE_TIMEOUT_S = 120
_caps_lock = threading.Lock()
_capabilities: dict | None = None

_PROBE_SCRIPT = """
import sys
import gpredomicspy
param = gpredomicspy.Param()
param.load(sys.argv[1])
experiment = gpredomicspy.fit(param)
assert len(experiment.best_population()) >= 0
"""


def _engine_identity() -> dict:
    version = getattr(gpredomicspy, "__version__", None) if HAS_ENGINE else None
    return {
        "version": version,
        "ref": os.environ.get("PREDOMICS_ENGINE_REF") or None,
        "bindings_ref": os.environ.get("PREDOMICS_ENGINEPY_REF") or None,
    }


def _caps_cache_path() -> Path:
    return Path(app_settings.data_dir) / "cache" / "engine_capabilities.json"


def _write_probe_data(folder: Path) -> tuple[str, str]:
    """A tiny, well-separated two-class dataset (features in rows)."""
    import random

    rng = random.Random(7)
    samples = [f"s{i}" for i in range(40)]
    labels = [0] * 20 + [1] * 20
    lines = ["feature\t" + "\t".join(samples)]
    for f in range(30):
        shift = (0.6 if f % 2 == 0 else -0.6)
        row = []
        for label in labels:
            base = rng.random() + (shift if label == 1 and f < 12 else 0.0)
            row.append("0" if (rng.random() < 0.15 or base <= 0) else f"{base:.4f}")
        lines.append(f"f{f}\t" + "\t".join(row))
    x_path, y_path = folder / "X.tsv", folder / "y.tsv"
    x_path.write_text("\n".join(lines) + "\n")
    y_path.write_text("sample\tclass\n" + "".join(f"{s}\t{c}\n" for s, c in zip(samples, labels)))
    return str(x_path), str(y_path)


def _probe(languages: list[str], data_types: list[str]) -> tuple[bool, str]:
    """Run a very small real fit in a subprocess. Returns (worked, last output line)."""
    with tempfile.TemporaryDirectory(prefix="predomics-probe-") as tmp:
        folder = Path(tmp)
        x_path, y_path = _write_probe_data(folder)
        config = {
            "general": {"algo": "ga", "language": ",".join(languages), "data_type": ",".join(data_types),
                        "fit": "auc", "seed": 1, "thread_number": 1, "cv": False, "gpu": False,
                        "keep_trace": False, "display_colorful": False, "log_level": "error"},
            "ga": {"population_size": 200, "max_epochs": 2, "min_epochs": 1, "k_min": 1, "k_max": 5,
                   "select_elite_pct": 10.0, "select_random_pct": 10.0},
            "data": {"feature_minimal_prevalence_pct": 0, "feature_maximal_adj_pvalue": 1.0,
                     "features_in_rows": True},
        }
        # admin_defaults={}: the probe must not depend on what an admin configured.
        param_path = write_param_yaml(config, x_path, y_path, output_dir=str(folder), admin_defaults={})
        try:
            proc = subprocess.run(
                [sys.executable, "-c", _PROBE_SCRIPT, param_path],
                capture_output=True, text=True, timeout=_PROBE_TIMEOUT_S, cwd=str(folder),
            )
        except subprocess.TimeoutExpired:
            return False, "timed out"
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return proc.returncode == 0, (tail[-1] if tail else "")


def probe_capabilities(force: bool = False) -> dict:
    """Find out which data types and languages the installed engine supports.

    Blocking (a few seconds): each data type and each language is tried with a
    tiny real fit in a subprocess, so an engine panic cannot hurt this process.
    The answer is cached in ``<data_dir>/cache/engine_capabilities.json`` and
    reused while the engine version and source revision stay the same.
    """
    global _capabilities
    identity = _engine_identity()
    result: dict = {"available": HAS_ENGINE, **identity, "probed": False,
                    "data_types": [], "languages": [], "errors": {}}
    if HAS_ENGINE:
        cache_path = _caps_cache_path()
        cached = None
        if not force and cache_path.is_file():
            try:
                cached = json.loads(cache_path.read_text())
            except (OSError, ValueError):
                cached = None
        if cached and all(cached.get(k) == identity[k] for k in identity) and cached.get("probed"):
            result = cached
        else:
            for data_type in KNOWN_DATA_TYPES:
                ok, message = _probe(["bin"], [data_type])
                if ok:
                    result["data_types"].append(data_type)
                else:
                    result["errors"][f"data_type:{data_type}"] = message[-300:]
            base_type = "raw" if "raw" in result["data_types"] else (result["data_types"] or ["raw"])[0]
            for language in KNOWN_LANGUAGES:
                ok, message = _probe([language], [base_type])
                if ok:
                    result["languages"].append(language)
                else:
                    result["errors"][f"language:{language}"] = message[-300:]
            result["probed"] = True
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                tmp = cache_path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(result, indent=1))
                os.replace(tmp, cache_path)
            except OSError as exc:
                logger.warning("Could not cache engine capabilities: %s", exc)
    with _caps_lock:
        _capabilities = result
    return capabilities()


def capabilities() -> dict:
    """Engine capabilities and whether the server's default settings fit them.

    Cheap and safe to call from request handlers: it never probes. Until
    :func:`probe_capabilities` has run, ``probed`` is False and nothing is
    reported missing.

    Keys: ``available``, ``version``, ``ref``, ``bindings_ref``, ``probed``,
    ``data_types``, ``languages``, ``missing`` (default settings the engine cannot
    honour, e.g. ``["data_type:zscore"]``) and ``ok``.
    """
    with _caps_lock:
        caps = dict(_capabilities) if _capabilities is not None else {
            "available": HAS_ENGINE, **_engine_identity(), "probed": False,
            "data_types": [], "languages": [], "errors": {},
        }
    missing: list[str] = []
    if caps["available"] and caps["probed"]:
        general = _effective({}, "general", _GENERAL_DEFAULTS)   # hardcoded + admin defaults
        missing += [f"data_type:{d}" for d in _csv(general["data_type"]) if d not in caps["data_types"]]
        missing += [f"language:{l}" for l in _csv(general["language"]) if l not in caps["languages"]]
    caps["missing"] = missing
    caps["ok"] = bool(caps["available"]) and not missing
    caps.pop("errors", None)
    return caps


def check_startup_compatibility() -> dict:
    """Probe the engine and log what it can do (call once at startup, off the event loop).

    A default setting the engine cannot honour is logged as an error naming it,
    so the problem is visible at startup and in the health payload instead of as
    failed jobs later.
    """
    if not HAS_ENGINE:
        logger.error("gpredomicspy is not installed: analysis jobs cannot run on this server")
        return probe_capabilities()
    caps = probe_capabilities()
    logger.info(
        "Engine gpredomicspy %s (engine %s, bindings %s): data types %s; languages %s",
        caps.get("version") or "?", (caps.get("ref") or "unknown")[:12],
        (caps.get("bindings_ref") or "unknown")[:12],
        ",".join(caps["data_types"]) or "none", ",".join(caps["languages"]) or "none",
    )
    for item in caps["missing"]:
        kind, _, name = item.partition(":")
        logger.error(
            "The default %s '%s' is not supported by the installed engine. Jobs using the defaults "
            "will fail: install an engine that supports it or change the default (Admin > Defaults).",
            kind.replace("_", " "), name,
        )
    return caps


def write_param_yaml(
    config: dict[str, Any],
    x_path: str,
    y_path: str,
    xtest_path: str = "",
    ytest_path: str = "",
    clinical_path: str = "",
    output_dir: str = "/tmp",
    admin_defaults: dict | None = None,
) -> str:
    """Write a gpredomics param.yaml from API config dict.

    Merge order: hardcoded defaults ← admin defaults ← user config.
    Returns the path to the generated YAML file.
    """
    # Load admin defaults (flat keys like "general.language" -> "bin")
    if admin_defaults is None:
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
        "language": "bin,ter,ratio", "data_type": "raw,prev,zscore", "epsilon": 1e-5,
        "fit": "auc", "k_penalty": 0.0001, "fr_penalty": 0.0, "bias_penalty": 0.0,
        "threshold_ci_n_bootstrap": 0, "threshold_ci_penalty": 0.5,
        "threshold_ci_alpha": 0.05, "threshold_ci_frac_bootstrap": 1.0,
        "user_feature_penalties_weight": 1.0, "n_model_to_display": 30,
        "log_level": "info", "keep_trace": True, "display_colorful": True,
        "save_exp": str(Path(output_dir) / "experiment.bin"),
    })

    # gpredomics reads the prevalence/log/ratio epsilon from `data_type_epsilon`;
    # the `epsilon` key alone is accepted but ignored by the engine.
    general["data_type_epsilon"] = general.get("epsilon", 1e-5)

    # When fit is a regression function, disable class-based feature selection
    is_regression = general.get("fit") in REGRESSION_FIT_FUNCTIONS

    data_cfg = config.get("data", {})
    # Feature selection params may come from a separate "feature_selection" category in the UI
    fs_cfg = config.get("feature_selection", {})
    data_cfg = {**data_cfg, **fs_cfg}  # feature_selection overrides data defaults

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


def _mock_results() -> dict[str, Any]:
    """Return fabricated results for tests/development when gpredomicspy is missing.

    Only used when ``settings.allow_mock_engine`` or ``settings.debug`` is set;
    the payload is labelled ``"mock": True`` so it can never pass for a real run.
    """
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
                "data_type": rng.choice(["raw", "prev", "zscore"]),
            },
            "features": {},
            "named_features": {f"feature_{rng.randint(0, 49)}": rng.choice([-1, 1]) for _ in range(3)},
        })

    return {
        "mock": True,
        "engine": "mock",
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
