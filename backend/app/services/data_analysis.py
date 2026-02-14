"""Data analysis service — wraps gpredomicspy.filter_features() for the Data Explore tab."""

from __future__ import annotations
import logging
import time
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)

# Try to import gpredomicspy
try:
    import gpredomicspy
    HAS_ENGINE = True
except ImportError:
    HAS_ENGINE = False
    logger.warning("gpredomicspy not installed — data analysis will use mock mode")

# Simple TTL cache: (x_path, y_path, method, prevalence, pvalue) -> (timestamp, result)
_cache: dict[tuple, tuple[float, dict]] = {}
_CACHE_TTL = 300  # 5 minutes


def _cache_key(x_path: str, y_path: str, method: str, prevalence_pct: float, max_pvalue: float) -> tuple:
    return (x_path, y_path, method, prevalence_pct, max_pvalue)


def _get_cached(key: tuple) -> dict | None:
    if key in _cache:
        ts, result = _cache[key]
        if time.time() - ts < _CACHE_TTL:
            return result
        del _cache[key]
    return None


def _set_cached(key: tuple, result: dict) -> None:
    _cache[key] = (time.time(), result)
    # Evict old entries if cache grows too large
    if len(_cache) > 20:
        now = time.time()
        expired = [k for k, (ts, _) in _cache.items() if now - ts > _CACHE_TTL]
        for k in expired:
            del _cache[k]


def run_filtering(
    x_path: str,
    y_path: str,
    features_in_rows: bool = True,
    method: str = "wilcoxon",
    prevalence_pct: float = 10.0,
    max_pvalue: float = 0.05,
    min_feature_value: float = 0.0,
) -> dict[str, Any]:
    """Run feature filtering via gpredomicspy (Rust engine).

    Returns a dict with n_features, n_samples, class info, and per-feature stats.
    Falls back to mock data if gpredomicspy is not available.
    """
    key = _cache_key(x_path, y_path, method, prevalence_pct, max_pvalue)
    cached = _get_cached(key)
    if cached is not None:
        return cached

    if not HAS_ENGINE:
        result = _mock_filtering(method)
        _set_cached(key, result)
        return result

    # Build a param YAML and load it
    cfg = {
        "data": {
            "X": x_path,
            "y": y_path,
            "features_in_rows": features_in_rows,
            "feature_selection_method": method,
            "feature_minimal_prevalence_pct": prevalence_pct,
            "feature_maximal_adj_pvalue": max_pvalue,
            "feature_minimal_feature_value": min_feature_value,
        },
        "general": {"algo": "ga", "seed": 42, "thread_number": 4},
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(cfg, f, default_flow_style=False)
        yaml_path = f.name

    try:
        param = gpredomicspy.Param()
        param.load(yaml_path)
        raw = gpredomicspy.filter_features(param)

        # Convert PyO3 result to plain Python dicts
        result = {
            "n_features": raw["n_features"],
            "n_samples": raw["n_samples"],
            "n_classes": max(2, raw["n_classes"]),  # at least 2 classes
            "class_labels": list(raw.get("class_labels", [])) or ["0", "1"],
            "class_counts": dict(raw["class_counts"]),
            "feature_names": list(raw["feature_names"]),
            "features": [dict(f) for f in raw["features"]],
            "selected_count": raw["selected_count"],
            "method": raw["method"],
        }

        _set_cached(key, result)
        return result
    finally:
        Path(yaml_path).unlink(missing_ok=True)


def compute_distributions(features: list[dict]) -> dict[str, Any]:
    """Compute histogram distributions from feature stats.

    Returns pre-binned data for prevalence and SD histograms.
    """
    prevalences = [f["prevalence"] for f in features]
    stds = [f["std"] for f in features]

    prev_counts, prev_edges = np.histogram(prevalences, bins=20, range=(0, 100))
    sd_counts, sd_edges = np.histogram(stds, bins=30)

    return {
        "prevalence_histogram": {
            "bin_edges": prev_edges.tolist(),
            "counts": prev_counts.tolist(),
        },
        "sd_histogram": {
            "bin_edges": sd_edges.tolist(),
            "counts": sd_counts.tolist(),
        },
    }


def compute_feature_abundance(
    x_path: str,
    y_path: str,
    feature_names: list[str],
    features_in_rows: bool = True,
) -> list[dict[str, Any]]:
    """Compute boxplot summary stats per class for selected features.

    Uses pandas to load data and compute quartiles. Max 100 features.
    """
    feature_names = feature_names[:100]

    X = pd.read_csv(x_path, sep="\t", index_col=0)
    y = pd.read_csv(y_path, sep="\t", index_col=0)

    if features_in_rows:
        X = X.T  # now rows=samples, cols=features

    y_series = y.iloc[:, 0]
    common = X.index.intersection(y_series.index)
    X = X.loc[common]
    y_series = y_series.loc[common]

    results = []
    for fname in feature_names:
        if fname not in X.columns:
            continue

        values = X[fname].astype(float)
        classes_data = {}

        for cls_val in sorted(y_series.unique()):
            cls_values = values[y_series == cls_val].dropna()
            if len(cls_values) == 0:
                continue
            q1, median, q3 = cls_values.quantile([0.25, 0.5, 0.75]).values
            classes_data[str(int(cls_val))] = {
                "min": float(cls_values.min()),
                "q1": float(q1),
                "median": float(median),
                "q3": float(q3),
                "max": float(cls_values.max()),
                "mean": float(cls_values.mean()),
                "n": len(cls_values),
            }

        results.append({
            "name": fname,
            "classes": classes_data,
        })

    return results


def compute_barcode_data(
    x_path: str,
    y_path: str,
    feature_names: list[str],
    features_in_rows: bool = True,
    max_samples: int = 500,
) -> dict[str, Any]:
    """Compute barcode heatmap data: raw feature values per sample, ordered by class.

    Returns a matrix (features x samples) plus metadata for heatmap rendering.
    """
    feature_names = feature_names[:100]

    X = pd.read_csv(x_path, sep="\t", index_col=0)
    y = pd.read_csv(y_path, sep="\t", index_col=0)

    if features_in_rows:
        X = X.T  # rows=samples, cols=features

    y_series = y.iloc[:, 0]
    common = X.index.intersection(y_series.index)
    X = X.loc[common]
    y_series = y_series.loc[common]

    # Filter to requested features that exist
    valid_features = [f for f in feature_names if f in X.columns]
    if not valid_features:
        return {
            "matrix": [], "feature_names": [], "sample_names": [],
            "sample_classes": [], "class_labels": [], "class_boundaries": [],
        }

    # Sort samples by class
    sort_order = y_series.sort_values().index
    X_sorted = X.loc[sort_order, valid_features]
    y_sorted = y_series.loc[sort_order]

    # Stratified subsampling if too many samples
    if len(X_sorted) > max_samples:
        sampled_indices = []
        for cls in sorted(y_sorted.unique()):
            cls_indices = y_sorted[y_sorted == cls].index.tolist()
            n_cls = max(1, int(max_samples * len(cls_indices) / len(y_sorted)))
            step = max(1, len(cls_indices) // n_cls)
            sampled_indices.extend(cls_indices[::step][:n_cls])
        X_sorted = X_sorted.loc[sampled_indices]
        y_sorted = y_sorted.loc[sampled_indices]

    # Compute class boundaries (cumulative count where each class ends)
    class_labels = sorted(y_sorted.unique())
    class_boundaries = []
    cumulative = 0
    for cls in class_labels[:-1]:
        cumulative += int((y_sorted == cls).sum())
        class_boundaries.append(cumulative)

    # Build matrix (features x samples)
    matrix = X_sorted[valid_features].T.values.tolist()

    return {
        "matrix": matrix,
        "feature_names": valid_features,
        "sample_names": X_sorted.index.tolist(),
        "sample_classes": y_sorted.astype(int).tolist(),
        "class_labels": [str(int(c)) for c in class_labels],
        "class_boundaries": class_boundaries,
    }


def _mock_filtering(method: str = "wilcoxon") -> dict[str, Any]:
    """Return mock filtering results when gpredomicspy is not available."""
    import random
    rng = random.Random(42)

    n_features = 50
    n_samples = 100
    features = []
    for i in range(n_features):
        selected = rng.random() < 0.4
        features.append({
            "index": i,
            "name": f"feature_{i}",
            "selected": selected,
            "class": rng.choice([0, 1]) if selected else 2,
            "significance": round(rng.uniform(0.0001, 0.05), 6) if selected else None,
            "mean": round(rng.uniform(0, 0.01), 6),
            "std": round(rng.uniform(0, 0.005), 6),
            "prevalence": round(rng.uniform(0, 100), 1),
            "mean_0": round(rng.uniform(0, 0.01), 6),
            "mean_1": round(rng.uniform(0, 0.01), 6),
            "std_0": round(rng.uniform(0, 0.005), 6),
            "std_1": round(rng.uniform(0, 0.005), 6),
            "prevalence_0": round(rng.uniform(0, 100), 1),
            "prevalence_1": round(rng.uniform(0, 100), 1),
        })

    return {
        "n_features": n_features,
        "n_samples": n_samples,
        "n_classes": 2,
        "class_labels": ["0", "1"],
        "class_counts": {"0": 55, "1": 45},
        "feature_names": [f"feature_{i}" for i in range(n_features)],
        "features": features,
        "selected_count": sum(1 for f in features if f["selected"]),
        "method": method,
    }
