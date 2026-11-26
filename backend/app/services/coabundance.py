"""Co-abundance ecosystem network service.

Computes species co-abundance networks from the abundance matrix using
Spearman correlation, with community detection and taxonomic
coloring inspired by the Interpred approach and SCAPIS ecosystem code.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from . import matrix_io
from . import msp_annotations
from .taxonomy_colors import assign_taxonomy_colors, MODULE_COLORS

logger = logging.getLogger(__name__)

# TTL cache for network computation results
_cache: dict[tuple, tuple[float, dict]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 600  # 10 minutes
_CACHE_MAX = 10


def _file_state(path: str) -> tuple:
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return (0, 0)


def _cache_key(
    x_path: str, y_path: str, min_prevalence_pct: float,
    correlation_threshold: float, class_filter: str,
    features_csv: str, community_method: str = "louvain",
    features_in_rows: bool = True, job_key: str = "",
) -> tuple:
    return (
        x_path, y_path, min_prevalence_pct, correlation_threshold, class_filter,
        features_csv, community_method, bool(features_in_rows), job_key,
        _file_state(x_path), _file_state(y_path),
    )


def _get_cached(key: tuple) -> dict | None:
    with _cache_lock:
        hit = _cache.get(key)
        if hit is None:
            return None
        ts, result = hit
        if time.time() - ts < _CACHE_TTL:
            return result
        del _cache[key]
    return None


def _set_cached(key: tuple, result: dict) -> None:
    now = time.time()
    with _cache_lock:
        _cache[key] = (now, result)
        for k in [k for k, (ts, _) in _cache.items() if now - ts > _CACHE_TTL]:
            del _cache[k]
        while len(_cache) > _CACHE_MAX:
            del _cache[min(_cache, key=lambda k: _cache[k][0])]


def spearman_matrix(mat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Spearman correlation and two-sided p-value matrices for the columns of ``mat``.

    Vectorised (average ranks, then Pearson on the ranks; p-values from the
    t distribution with n-2 degrees of freedom) — the same statistic as
    ``scipy.stats.spearmanr`` without a Python loop over feature pairs.
    Constant columns give NaN correlations.
    """
    n = mat.shape[0]
    ranks = stats.rankdata(mat, axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        rho = np.corrcoef(ranks, rowvar=False)
        rho = np.atleast_2d(rho)
        dof = n - 2
        if dof > 0:
            r = np.clip(rho, -1.0, 1.0)
            t = r * np.sqrt(dof / ((1.0 - r) * (1.0 + r)))
            pval = 2.0 * stats.t.sf(np.abs(t), dof)
        else:
            pval = np.full_like(rho, np.nan)
    return rho, pval


def _detect_communities(G, method: str = "louvain", seed: int = 42) -> list:
    """Dispatch community detection to the chosen algorithm.

    Supported methods:
      - "louvain": Louvain modularity optimization (default)
      - "greedy": Greedy modularity maximization
      - "label_propagation": Asynchronous label propagation

    Falls back to one-community-per-node on any error.
    """
    import networkx as nx

    try:
        if method == "louvain":
            communities = nx.community.louvain_communities(G, seed=seed)
        elif method == "greedy":
            communities = nx.community.greedy_modularity_communities(G)
        elif method == "label_propagation":
            communities = list(nx.community.label_propagation_communities(G))
        else:
            # Unknown method — fall back to Louvain
            logger.warning("Unknown community method '%s', falling back to louvain", method)
            communities = nx.community.louvain_communities(G, seed=seed)
    except Exception:
        logger.warning("Community detection '%s' failed, falling back to singletons", method)
        communities = [{n} for n in G.nodes()]

    return communities


def compute_coabundance_network(
    x_path: str,
    y_path: str,
    features_in_rows: bool = True,
    min_prevalence_pct: float = 30.0,
    correlation_threshold: float = 0.3,
    class_filter: str = "all",
    feature_names: list[str] | None = None,
    job_results: dict | None = None,
    community_method: str = "louvain",
) -> dict[str, Any]:
    """Compute a co-abundance network from the abundance matrix.

    Args:
        x_path: Path to Xtrain TSV file.
        y_path: Path to Ytrain TSV file.
        features_in_rows: Whether features are in rows (transposed to samples×features).
        min_prevalence_pct: Minimum prevalence (%) to include a feature.
        correlation_threshold: Minimum |Spearman rho| for an edge.
        class_filter: "all", "0", or "1" — which class samples to use.
        feature_names: Optional feature subset (e.g., FBM features from a job).
        job_results: Optional job results dict for FBM annotation.

    Returns:
        Dict with nodes, edges, modules, taxonomy_legend, stats.
    """
    features_csv = ",".join(sorted(feature_names)) if feature_names else ""
    # The result embeds FBM annotations from `job_results`, so they are part of the key.
    job_key = ""
    if job_results:
        pop = job_results.get("population", [])
        first = sorted((pop[0].get("named_features") or {}).items()) if pop else []
        job_key = f"{job_results.get('execution_time')}:{len(pop)}:{hash(str(first))}"
    key = _cache_key(
        x_path, y_path, min_prevalence_pct, correlation_threshold, class_filter,
        features_csv, community_method, features_in_rows, job_key,
    )
    cached = _get_cached(key)
    if cached is not None:
        return cached

    t0 = time.time()

    # --- Load data once (cached, aligned by sample name) ---
    X_full, y_full = matrix_io.load_xy(x_path, y_path, features_in_rows)
    y_full = pd.to_numeric(y_full, errors="coerce")
    keep = y_full.notna().to_numpy()
    X_full, y_full = X_full.loc[keep], y_full.loc[keep]
    matrix_io.class_codes(y_full)  # clear error for non-class labels

    X, y_series = X_full, y_full
    n_features_total = X.shape[1]

    # --- Filter to specific features if provided ---
    if feature_names:
        valid = [f for f in feature_names if f in X.columns]
        if valid:
            X = X[valid]

    # --- Filter by class ---
    if class_filter in ("0", "1"):
        cls_val = int(class_filter)
        mask = (y_series == cls_val).to_numpy()
        X = X.loc[mask]
        y_series = y_series.loc[mask]

    # --- Filter features by prevalence ---
    n_samples = X.shape[0]
    if n_samples == 0:
        return _empty_result(n_features_total)
    prevalence = (X > 0).sum(axis=0) / n_samples * 100
    kept_features = prevalence[prevalence >= min_prevalence_pct].index.tolist()

    if len(kept_features) < 2:
        return _empty_result(n_features_total)

    X_filtered = X[kept_features]
    n_features_filtered = len(kept_features)

    # --- Per-class prevalence over all samples ---
    class_labels = sorted([str(int(c)) for c in y_full.unique()])
    prevalence_by_class: dict[str, dict[str, float]] = {}
    for cls_label in class_labels:
        cls_mask = (y_full == int(cls_label)).to_numpy()
        n_cls = int(cls_mask.sum())
        if n_cls > 0:
            prev = (X_full.loc[cls_mask, kept_features] > 0).sum(axis=0) / n_cls
            prevalence_by_class[cls_label] = prev.to_dict()
        else:
            prevalence_by_class[cls_label] = {f: 0.0 for f in kept_features}

    # --- Compute pairwise Spearman correlations (vectorised) ---
    mat = np.nan_to_num(X_filtered.to_numpy(dtype=float), nan=0.0)
    n_feat = mat.shape[1]
    if mat.shape[0] < 3:
        return _empty_result(n_features_total, n_features_filtered)
    corr_matrix, pval_matrix = spearman_matrix(mat)

    # --- Build edge list ---
    iu, ju = np.triu_indices(n_feat, k=1)
    rho_u = corr_matrix[iu, ju]
    sel = ~np.isnan(rho_u) & (np.abs(rho_u) >= correlation_threshold)
    edges = [
        {
            "source": kept_features[i],
            "target": kept_features[j],
            "correlation": round(float(r), 4),
            "pvalue": round(float(p), 6) if not np.isnan(p) else 1.0,
        }
        for i, j, r, p in zip(iu[sel], ju[sel], rho_u[sel], pval_matrix[iu, ju][sel])
    ]

    if not edges:
        return _empty_result(n_features_total, n_features_filtered)

    # --- Build networkx graph + community detection ---
    import networkx as nx

    G = nx.Graph()
    # Add all filtered features as nodes (even isolated ones after edge filtering)
    edge_nodes = set()
    for e in edges:
        edge_nodes.add(e["source"])
        edge_nodes.add(e["target"])
        G.add_edge(e["source"], e["target"], weight=abs(e["correlation"]))

    # Only include nodes that have at least one edge
    node_ids = sorted(edge_nodes)

    # Community detection (configurable method)
    communities = _detect_communities(G, method=community_method, seed=42)
    try:
        modularity = nx.community.modularity(G, communities)
    except Exception:
        modularity = 0.0

    node_module: dict[str, int] = {}
    for mod_idx, comm in enumerate(communities):
        for n in comm:
            node_module[n] = mod_idx

    # Node metrics
    degrees = dict(G.degree())
    try:
        betweenness = nx.betweenness_centrality(G)
    except Exception:
        betweenness = {n: 0.0 for n in node_ids}

    # Mean abundance per feature
    mean_abundance = X_filtered.mean(axis=0).to_dict()

    # --- Fetch taxonomy annotations ---
    annotations = msp_annotations.get_annotations(node_ids)

    # --- Build node list ---
    nodes_for_coloring = []
    for nid in node_ids:
        ann = annotations.get(nid, {})
        nodes_for_coloring.append({
            "id": nid,
            "phylum": ann.get("phylum", None),
            "family": ann.get("family", None),
        })

    family_colors, legend_entries = assign_taxonomy_colors(nodes_for_coloring)

    # --- FBM annotation (if job results provided) ---
    fbm_data = _compute_fbm_annotation(job_results, node_ids) if job_results else {}

    # --- Assemble nodes ---
    nodes = []
    for nid in node_ids:
        ann = annotations.get(nid, {})
        phy = ann.get("phylum", "Unknown")
        fam = ann.get("family", "Unknown")

        prev_0 = prevalence_by_class.get("0", {}).get(nid, 0.0)
        prev_1 = prevalence_by_class.get("1", {}).get(nid, 0.0)
        enriched = 1 if prev_1 > prev_0 else 0

        fbm = fbm_data.get(nid, {})

        nodes.append({
            "id": nid,
            "species": ann.get("species", nid),
            "phylum": phy,
            "family": fam,
            "genus": ann.get("genus", None),
            "color": family_colors.get(fam, "#999999"),
            "module": node_module.get(nid, 0),
            "degree": degrees.get(nid, 0),
            "betweenness": round(betweenness.get(nid, 0.0), 4),
            "mean_abundance": round(mean_abundance.get(nid, 0.0), 6),
            "prevalence_0": round(prev_0, 4),
            "prevalence_1": round(prev_1, 4),
            "enriched_class": enriched,
            "fbm_prevalence": fbm.get("prevalence"),
            "fbm_coefficient": fbm.get("coefficient"),
        })

    # --- Assemble modules ---
    modules = []
    for mod_idx, comm in enumerate(communities):
        # Only include modules that have nodes in our final node set
        comm_in_nodes = comm.intersection(edge_nodes)
        if not comm_in_nodes:
            continue
        # Dominant phylum
        phyla = [annotations.get(n, {}).get("phylum", "Unknown") for n in comm_in_nodes]
        if phyla:
            from collections import Counter
            dominant = Counter(phyla).most_common(1)[0][0]
        else:
            dominant = "Unknown"

        modules.append({
            "id": mod_idx,
            "size": len(comm_in_nodes),
            "color": MODULE_COLORS[mod_idx % len(MODULE_COLORS)],
            "dominant_phylum": dominant,
        })

    elapsed = time.time() - t0
    logger.info(
        "Co-abundance network: %d nodes, %d edges, %d modules (%.1fs)",
        len(nodes), len(edges), len(modules), elapsed,
    )

    result = {
        "nodes": nodes,
        "edges": edges,
        "modules": modules,
        "taxonomy_legend": legend_entries,
        "stats": {
            "n_features_total": n_features_total,
            "n_features_filtered": n_features_filtered,
            "n_nodes": len(nodes),
            "n_edges": len(edges),
            "n_modules": len(modules),
            "modularity": round(modularity, 4),
        },
    }

    _set_cached(key, result)
    return result


def _compute_fbm_annotation(
    job_results: dict, feature_ids: list[str],
) -> dict[str, dict]:
    """Extract FBM prevalence and dominant coefficient for each feature."""
    population = job_results.get("population", [])
    if not population:
        return {}

    n_models = len(population)
    feature_counts: dict[str, int] = {}
    coeff_sums: dict[str, int] = {}

    for ind in population:
        named = ind.get("named_features", {})
        for feat, coeff in named.items():
            if feat in feature_ids:
                feature_counts[feat] = feature_counts.get(feat, 0) + 1
                coeff_sums[feat] = coeff_sums.get(feat, 0) + int(coeff)

    result = {}
    for feat in feature_ids:
        count = feature_counts.get(feat, 0)
        if count > 0:
            result[feat] = {
                "prevalence": round(count / n_models, 4),
                "coefficient": 1 if coeff_sums.get(feat, 0) > 0 else (-1 if coeff_sums.get(feat, 0) < 0 else 0),
            }
    return result


def _empty_result(n_total: int = 0, n_filtered: int = 0) -> dict:
    return {
        "nodes": [],
        "edges": [],
        "modules": [],
        "taxonomy_legend": [],
        "stats": {
            "n_features_total": n_total,
            "n_features_filtered": n_filtered,
            "n_nodes": 0,
            "n_edges": 0,
            "n_modules": 0,
            "modularity": 0.0,
        },
    }
