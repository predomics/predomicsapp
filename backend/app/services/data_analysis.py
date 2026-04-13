"""Data analysis service — wraps gpredomicspy.filter_features() for the Data Explore tab."""

from __future__ import annotations
import logging
import time
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
import yaml

logger = logging.getLogger(__name__)

# Allowed data transformations for exploration and ordination
VALID_TRANSFORMS = ("raw", "log", "zscore")


def apply_transform(values: np.ndarray, transform: str = "raw", epsilon: float = 1e-5) -> np.ndarray:
    """Apply a data transformation to a feature × sample matrix.

    - raw: no transformation
    - log: natural log with epsilon flooring (values below epsilon → epsilon)
    - zscore: per-column (feature) standardization using mean/std
    """
    if transform == "raw" or transform is None:
        return values
    if transform == "log":
        return np.log(np.maximum(values, epsilon))
    if transform == "zscore":
        mean = np.nanmean(values, axis=0)
        std = np.nanstd(values, axis=0, ddof=0)
        std[std == 0] = 1.0  # avoid division by zero for constant features
        return (values - mean) / std
    raise ValueError(f"Unknown transform '{transform}', must be one of {VALID_TRANSFORMS}")


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
    transform: str = "raw",
) -> list[dict[str, Any]]:
    """Compute boxplot summary stats per class for selected features.

    Uses pandas to load data and compute quartiles. Max 100 features.
    Supports transformations: raw, log, zscore.
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

    # Apply transformation feature-wise (z-score uses per-feature stats)
    if transform != "raw":
        X_num = X[[c for c in X.columns if X[c].dtype.kind in "iuf"]].astype(float)
        transformed = apply_transform(X_num.values, transform=transform)
        X_num = pd.DataFrame(transformed, index=X_num.index, columns=X_num.columns)
        for c in X_num.columns:
            X[c] = X_num[c]

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


def compute_pcoa(
    x_path: str,
    y_path: str,
    features_in_rows: bool = True,
    metric: str = "braycurtis",
    max_samples: int = 1000,
    feature_names: list[str] | None = None,
    n_permutations: int = 999,
    transform: str = "raw",
) -> dict[str, Any]:
    """Compute PCoA with confidence ellipses and PERMANOVA.

    Uses scipy distance matrix + classical multidimensional scaling (eigendecomposition).
    Returns principal coordinates, sample metadata, % variance explained,
    per-class confidence ellipses, and PERMANOVA test results.

    If feature_names is provided, only those features are used (FBM filtering).
    """
    from scipy.spatial.distance import pdist, squareform

    X = pd.read_csv(x_path, sep="\t", index_col=0)
    y = pd.read_csv(y_path, sep="\t", index_col=0)

    if features_in_rows:
        X = X.T  # rows=samples, cols=features

    # Filter to specific features (FBM) if requested
    if feature_names:
        valid = [f for f in feature_names if f in X.columns]
        if valid:
            X = X[valid]
        # else keep all features as fallback

    y_series = y.iloc[:, 0]
    common = X.index.intersection(y_series.index)
    X = X.loc[common]
    y_series = y_series.loc[common]

    # Stratified subsampling if too many samples
    if len(X) > max_samples:
        sampled = []
        for cls in sorted(y_series.unique()):
            cls_idx = y_series[y_series == cls].index.tolist()
            n_cls = max(1, int(max_samples * len(cls_idx) / len(y_series)))
            step = max(1, len(cls_idx) // n_cls)
            sampled.extend(cls_idx[::step][:n_cls])
        X = X.loc[sampled]
        y_series = y_series.loc[sampled]

    mat = X.values.astype(float)
    # Replace NaN with 0 for distance computation
    mat = np.nan_to_num(mat, nan=0.0)

    # Apply data transformation (raw, log, zscore)
    mat = apply_transform(mat, transform=transform)

    # Compute pairwise distance matrix
    try:
        dists = pdist(mat, metric=metric)
    except ValueError:
        # Fallback to euclidean if metric not supported
        dists = pdist(mat, metric="euclidean")
        metric = "euclidean"

    D = squareform(dists)

    # Classical MDS (PCoA) via double-centering + eigendecomposition
    n = D.shape[0]
    H = np.eye(n) - np.ones((n, n)) / n  # centering matrix
    B = -0.5 * H @ (D ** 2) @ H

    eigenvalues, eigenvectors = np.linalg.eigh(B)

    # Sort by descending eigenvalue
    idx = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]

    # Take top 3 positive eigenvalues
    n_components = min(3, np.sum(eigenvalues > 0))
    if n_components == 0:
        # Degenerate case — return zeros
        coords = np.zeros((n, 3))
        variance_explained = [0.0, 0.0, 0.0]
    else:
        pos_eigenvalues = eigenvalues[:n_components]
        coords_partial = eigenvectors[:, :n_components] * np.sqrt(pos_eigenvalues)
        # Pad to 3 if fewer components
        coords = np.zeros((n, 3))
        coords[:, :n_components] = coords_partial

        total_positive = float(np.sum(eigenvalues[eigenvalues > 0]))
        variance_explained = [
            round(float(eigenvalues[i]) / total_positive * 100, 2) if i < n_components else 0.0
            for i in range(3)
        ]

    class_labels = sorted([str(int(c)) for c in y_series.unique()])
    y_int = y_series.astype(int).values

    # --- Confidence ellipses (95%) per class on PCo1 x PCo2 ---
    ellipses = _compute_ellipses(coords[:, :2], y_int, class_labels)

    # --- PERMANOVA on the distance matrix ---
    permanova = _compute_permanova(D, y_int, n_permutations=n_permutations)

    return {
        "coords": coords.tolist(),
        "sample_names": X.index.tolist(),
        "sample_classes": y_int.tolist(),
        "class_labels": class_labels,
        "variance_explained": variance_explained,
        "metric": metric,
        "n_samples": int(n),
        "n_features_used": int(X.shape[1]),
        "ellipses": ellipses,
        "permanova": permanova,
    }


def _compute_ellipses(
    coords_2d: np.ndarray,
    y: np.ndarray,
    class_labels: list[str],
    confidence: float = 0.95,
    n_points: int = 100,
) -> dict[str, dict]:
    """Compute 95% confidence ellipses for each class on 2D PCoA coordinates.

    Uses the covariance matrix eigendecomposition to define the ellipse
    axes and scales by the chi-squared critical value for the desired confidence.
    """
    from scipy.stats import chi2

    chi2_val = chi2.ppf(confidence, df=2)
    ellipses = {}

    for cls_str in class_labels:
        cls = int(cls_str)
        mask = y == cls
        pts = coords_2d[mask]

        if len(pts) < 3:
            continue

        cx, cy = pts[:, 0].mean(), pts[:, 1].mean()
        cov = np.cov(pts[:, 0], pts[:, 1])

        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        # Sort descending
        order = eigenvalues.argsort()[::-1]
        eigenvalues = eigenvalues[order]
        eigenvectors = eigenvectors[:, order]

        # Semi-axes scaled by chi-squared
        a = np.sqrt(eigenvalues[0] * chi2_val)
        b = np.sqrt(eigenvalues[1] * chi2_val)
        angle = np.arctan2(eigenvectors[1, 0], eigenvectors[0, 0])

        # Generate ellipse points
        theta = np.linspace(0, 2 * np.pi, n_points)
        cos_a, sin_a = np.cos(angle), np.sin(angle)
        ex = cx + a * np.cos(theta) * cos_a - b * np.sin(theta) * sin_a
        ey = cy + a * np.cos(theta) * sin_a + b * np.sin(theta) * cos_a

        ellipses[cls_str] = {
            "x": ex.tolist(),
            "y": ey.tolist(),
            "center": [float(cx), float(cy)],
        }

    return ellipses


def _compute_permanova(
    D: np.ndarray,
    y: np.ndarray,
    n_permutations: int = 999,
) -> dict[str, Any]:
    """Compute PERMANOVA (Permutational Multivariate Analysis of Variance).

    Tests whether group centroids differ significantly using the distance matrix.
    Returns F-statistic, R², p-value, and number of permutations.
    """
    n = len(y)
    classes = np.unique(y)
    a = len(classes)  # number of groups

    # Compute SS_total and SS_within from distance matrix
    D2 = D ** 2

    ss_total = np.sum(D2) / (2 * n)

    ss_within = 0.0
    for cls in classes:
        mask = y == cls
        ni = mask.sum()
        if ni < 2:
            continue
        ss_within += np.sum(D2[np.ix_(mask, mask)]) / (2 * ni)

    ss_between = ss_total - ss_within

    # F-statistic
    df_between = a - 1
    df_within = n - a
    if df_within <= 0 or ss_within == 0:
        return {"F": 0.0, "R2": 0.0, "p_value": 1.0, "n_permutations": 0}

    f_obs = (ss_between / df_between) / (ss_within / df_within)
    r2 = ss_between / ss_total

    # Permutation test
    rng = np.random.default_rng(42)
    n_ge = 0
    for _ in range(n_permutations):
        y_perm = rng.permutation(y)
        ss_within_perm = 0.0
        for cls in classes:
            mask_p = y_perm == cls
            ni = mask_p.sum()
            if ni < 2:
                continue
            ss_within_perm += np.sum(D2[np.ix_(mask_p, mask_p)]) / (2 * ni)
        ss_between_perm = ss_total - ss_within_perm
        f_perm = (ss_between_perm / df_between) / (ss_within_perm / df_within) if ss_within_perm > 0 else 0.0
        if f_perm >= f_obs:
            n_ge += 1

    p_value = (n_ge + 1) / (n_permutations + 1)

    return {
        "F": round(float(f_obs), 4),
        "R2": round(float(r2), 4),
        "p_value": round(float(p_value), 4),
        "n_permutations": n_permutations,
    }


def _load_and_prepare(
    x_path: str,
    y_path: str,
    features_in_rows: bool = True,
    metric: str = "braycurtis",
    max_samples: int = 1000,
    feature_names: list[str] | None = None,
    transform: str = "raw",
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str], list[str], str, int]:
    """Shared data loading for ordination methods (PCoA / t-SNE / UMAP).

    Returns (distance_matrix, coords_placeholder, y_int, sample_names,
             class_labels, metric, n_features_used).
    """
    from scipy.spatial.distance import pdist, squareform

    X = pd.read_csv(x_path, sep="\t", index_col=0)
    y = pd.read_csv(y_path, sep="\t", index_col=0)

    if features_in_rows:
        X = X.T

    if feature_names:
        valid = [f for f in feature_names if f in X.columns]
        if valid:
            X = X[valid]

    y_series = y.iloc[:, 0]
    common = X.index.intersection(y_series.index)
    X = X.loc[common]
    y_series = y_series.loc[common]

    if len(X) > max_samples:
        sampled = []
        for cls in sorted(y_series.unique()):
            cls_idx = y_series[y_series == cls].index.tolist()
            n_cls = max(1, int(max_samples * len(cls_idx) / len(y_series)))
            step = max(1, len(cls_idx) // n_cls)
            sampled.extend(cls_idx[::step][:n_cls])
        X = X.loc[sampled]
        y_series = y_series.loc[sampled]

    mat = X.values.astype(float)
    mat = np.nan_to_num(mat, nan=0.0)

    # Apply data transformation (raw, log, zscore)
    mat = apply_transform(mat, transform=transform)

    try:
        dists = pdist(mat, metric=metric)
    except ValueError:
        dists = pdist(mat, metric="euclidean")
        metric = "euclidean"

    D = squareform(dists)
    class_labels = sorted([str(int(c)) for c in y_series.unique()])
    y_int = y_series.astype(int).values
    sample_names = X.index.tolist()
    n_features_used = int(X.shape[1])

    return D, y_int, sample_names, class_labels, metric, n_features_used


def compute_tsne(
    x_path: str,
    y_path: str,
    features_in_rows: bool = True,
    metric: str = "euclidean",
    max_samples: int = 1000,
    feature_names: list[str] | None = None,
    n_permutations: int = 999,
    perplexity: float = 30.0,
    n_components: int = 2,
    transform: str = "raw",
) -> dict[str, Any]:
    """Compute t-SNE embedding with confidence ellipses and PERMANOVA.

    Uses precomputed distance matrix with sklearn.manifold.TSNE.
    """
    from sklearn.manifold import TSNE

    D, y_int, sample_names, class_labels, metric, n_features_used = _load_and_prepare(
        x_path, y_path, features_in_rows, metric, max_samples, feature_names, transform=transform,
    )
    n = D.shape[0]

    # Clamp perplexity to valid range (must be < n_samples)
    perplexity = min(perplexity, max(1.0, (n - 1) / 3.0))

    n_comp = min(n_components, 3)
    tsne = TSNE(
        n_components=n_comp,
        metric="precomputed",
        perplexity=perplexity,
        random_state=42,
        init="random",
    )
    coords_partial = tsne.fit_transform(D)

    # Pad to 3 dimensions
    coords = np.zeros((n, 3))
    coords[:, :n_comp] = coords_partial

    ellipses = _compute_ellipses(coords[:, :2], y_int, class_labels)
    permanova = _compute_permanova(D, y_int, n_permutations=n_permutations)

    return {
        "coords": coords.tolist(),
        "sample_names": sample_names,
        "sample_classes": y_int.tolist(),
        "class_labels": class_labels,
        "variance_explained": None,
        "metric": metric,
        "n_samples": int(n),
        "n_features_used": n_features_used,
        "ellipses": ellipses,
        "permanova": permanova,
        "method": "tsne",
        "params": {"perplexity": float(perplexity)},
    }


def compute_umap(
    x_path: str,
    y_path: str,
    features_in_rows: bool = True,
    metric: str = "braycurtis",
    max_samples: int = 1000,
    feature_names: list[str] | None = None,
    n_permutations: int = 999,
    n_neighbors: int = 15,
    min_dist: float = 0.1,
    n_components: int = 2,
    transform: str = "raw",
) -> dict[str, Any]:
    """Compute UMAP embedding with confidence ellipses and PERMANOVA.

    Uses precomputed distance matrix with umap.UMAP.
    """
    import umap

    D, y_int, sample_names, class_labels, metric, n_features_used = _load_and_prepare(
        x_path, y_path, features_in_rows, metric, max_samples, feature_names, transform=transform,
    )
    n = D.shape[0]

    # Clamp n_neighbors to valid range
    n_neighbors = min(n_neighbors, n - 1)

    n_comp = min(n_components, 3)
    reducer = umap.UMAP(
        n_components=n_comp,
        metric="precomputed",
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        random_state=42,
    )
    coords_partial = reducer.fit_transform(D)

    # Pad to 3 dimensions
    coords = np.zeros((n, 3))
    coords[:, :n_comp] = coords_partial

    ellipses = _compute_ellipses(coords[:, :2], y_int, class_labels)
    permanova = _compute_permanova(D, y_int, n_permutations=n_permutations)

    return {
        "coords": coords.tolist(),
        "sample_names": sample_names,
        "sample_classes": y_int.tolist(),
        "class_labels": class_labels,
        "variance_explained": None,
        "metric": metric,
        "n_samples": int(n),
        "n_features_used": n_features_used,
        "ellipses": ellipses,
        "permanova": permanova,
        "method": "umap",
        "params": {"n_neighbors": n_neighbors, "min_dist": float(min_dist)},
    }


def scan_dataset_metadata(
    x_path: str,
    y_path: str,
    features_in_rows: bool = True,
) -> dict[str, Any]:
    """Lightweight metadata scan using pandas only (no Rust engine needed).

    Reads file headers and y-values to extract dimensions and class info.
    Much faster than run_filtering() since it doesn't do statistical testing.
    """
    from datetime import datetime, timezone

    X = pd.read_csv(x_path, sep="\t", index_col=0)
    y = pd.read_csv(y_path, sep="\t", index_col=0)

    if features_in_rows:
        feature_names = X.index.tolist()
        sample_names = X.columns.tolist()
    else:
        feature_names = X.columns.tolist()
        sample_names = X.index.tolist()

    y_series = y.iloc[:, 0]
    class_labels = sorted([str(int(c)) for c in y_series.unique()])
    class_counts = {str(int(k)): int(v) for k, v in y_series.value_counts().items()}

    return {
        "n_features": len(feature_names),
        "n_samples": len(sample_names),
        "n_classes": len(class_labels),
        "class_labels": class_labels,
        "class_counts": class_counts,
        "sample_names": sample_names,
        "feature_names": feature_names,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }


def compute_aberrant_correlations(
    x_path: str, y_path: str, features_in_rows: bool = True,
    min_prevalence_pct: float = 30.0, max_pairs: int = 5000,
) -> dict:
    """Compute Spearman correlations per class for aberrant correlation diagnostic.

    Returns scatter data: for each feature pair, the correlation in class 0 vs class 1.
    """
    X = pd.read_csv(x_path, sep="\t", index_col=0)
    y = pd.read_csv(y_path, sep="\t", index_col=0)
    if features_in_rows:
        X = X.T
    y_series = y.iloc[:, 0]
    common = X.index.intersection(y_series.index)
    X, y_series = X.loc[common], y_series.loc[common]

    # Prevalence filter
    n_samples = X.shape[0]
    prevalence = (X > 0).sum(axis=0) / n_samples * 100
    kept = prevalence[prevalence >= min_prevalence_pct].index.tolist()
    if len(kept) < 2:
        return {"pairs": [], "n_features": 0, "n_pairs": 0}

    # Split by class
    mask0 = y_series == 0
    mask1 = y_series == 1
    X0 = X.loc[mask0, kept].values.astype(float)
    X1 = X.loc[mask1, kept].values.astype(float)
    X0 = np.nan_to_num(X0, nan=0.0)
    X1 = np.nan_to_num(X1, nan=0.0)

    n_feat = len(kept)
    # Compute full correlation matrices per class
    if n_feat <= 500:
        rho0, _ = stats.spearmanr(X0, axis=0) if X0.shape[0] > 2 else (np.zeros((n_feat, n_feat)), None)
        rho1, _ = stats.spearmanr(X1, axis=0) if X1.shape[0] > 2 else (np.zeros((n_feat, n_feat)), None)
        if n_feat == 2:
            rho0 = np.array([[1.0, rho0], [rho0, 1.0]])
            rho1 = np.array([[1.0, rho1], [rho1, 1.0]])
    else:
        # Subsample features
        rng = np.random.RandomState(42)
        idx = rng.choice(n_feat, 500, replace=False)
        idx.sort()
        kept = [kept[i] for i in idx]
        n_feat = 500
        X0 = X.loc[mask0, kept].values.astype(float)
        X1 = X.loc[mask1, kept].values.astype(float)
        rho0, _ = stats.spearmanr(X0, axis=0)
        rho1, _ = stats.spearmanr(X1, axis=0)

    # Collect pairs (upper triangle)
    pairs = []
    for i in range(n_feat):
        for j in range(i + 1, n_feat):
            r0 = float(rho0[i, j]) if not np.isnan(rho0[i, j]) else 0.0
            r1 = float(rho1[i, j]) if not np.isnan(rho1[i, j]) else 0.0
            pairs.append({"r0": round(r0, 4), "r1": round(r1, 4), "f1": kept[i], "f2": kept[j]})
            if len(pairs) >= max_pairs:
                break
        if len(pairs) >= max_pairs:
            break

    return {
        "pairs": pairs,
        "n_features": n_feat,
        "n_pairs": len(pairs),
        "feature_names": kept,
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
