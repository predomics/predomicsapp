"""Unit tests for backend services (no FastAPI/DB dependency)."""
from __future__ import annotations

import time

import networkx as nx
import numpy as np
import pandas as pd
import pytest

from app.services.stability import (
    _build_binary_matrix,
    _tanimoto_distance_matrix,
    _kuncheva_from_binary,
    _cw_rel_from_binary,
    compute_stability_analysis,
    _compute_feature_sparsity_heatmap,
)
from app.services.prediction import (
    predict_from_model,
    _compute_auc,
    parse_tsv,
)
from app.services.coabundance import (
    _detect_communities,
    _cache_key,
    _get_cached,
    _set_cached,
    _compute_fbm_annotation,
    _empty_result,
    _cache,
)


# ============================================================================
# Helpers
# ============================================================================

def _make_model(index: int, k: int, features: set, auc: float = 0.85, accuracy: float = 0.80) -> dict:
    """Create a model dict matching the structure used by stability service."""
    return {
        "index": index,
        "k": k,
        "auc": auc,
        "accuracy": accuracy,
        "features": features,
        "label": f"M{index}_k{k}",
    }


def _make_population_individual(features_dict: dict, named_features: dict | None = None,
                                 auc: float = 0.85, accuracy: float = 0.80, k: int | None = None) -> dict:
    """Create a population individual dict matching the structure expected by compute_stability_analysis."""
    ind = {
        "features": features_dict,
        "metrics": {
            "auc": auc,
            "accuracy": accuracy,
        },
    }
    if k is not None:
        ind["metrics"]["k"] = k
    if named_features is not None:
        ind["named_features"] = named_features
    return ind


def _small_graph() -> nx.Graph:
    """Build a small graph with two clear clusters for community detection tests."""
    G = nx.Graph()
    # Cluster 1: tightly connected
    G.add_edge("A", "B", weight=1.0)
    G.add_edge("B", "C", weight=1.0)
    G.add_edge("A", "C", weight=1.0)
    # Cluster 2: tightly connected
    G.add_edge("D", "E", weight=1.0)
    G.add_edge("E", "F", weight=1.0)
    G.add_edge("D", "F", weight=1.0)
    # Weak bridge between clusters
    G.add_edge("C", "D", weight=0.1)
    return G


# ============================================================================
# 1. Stability service tests
# ============================================================================

class TestBuildBinaryMatrix:
    """Tests for _build_binary_matrix."""

    def test_build_binary_matrix(self):
        """3 models, 5 features: verify matrix shape and values."""
        features = ["f1", "f2", "f3", "f4", "f5"]
        feature_to_idx = {f: i for i, f in enumerate(features)}

        models = [
            _make_model(0, 3, {"f1", "f2", "f3"}),
            _make_model(1, 2, {"f2", "f4"}),
            _make_model(2, 3, {"f1", "f3", "f5"}),
        ]

        mat = _build_binary_matrix(models, feature_to_idx)

        assert mat.shape == (3, 5)
        # Model 0: f1=1, f2=1, f3=1, f4=0, f5=0
        np.testing.assert_array_equal(mat[0], [1, 1, 1, 0, 0])
        # Model 1: f1=0, f2=1, f3=0, f4=1, f5=0
        np.testing.assert_array_equal(mat[1], [0, 1, 0, 1, 0])
        # Model 2: f1=1, f2=0, f3=1, f4=0, f5=1
        np.testing.assert_array_equal(mat[2], [1, 0, 1, 0, 1])


class TestTanimotoDistanceMatrix:
    """Tests for _tanimoto_distance_matrix."""

    def test_tanimoto_distance_identical(self):
        """Identical binary vectors should give distance 0."""
        mat = np.array([[1, 0, 1, 1], [1, 0, 1, 1]], dtype=np.float32)
        dist = _tanimoto_distance_matrix(mat)
        assert dist.shape == (2, 2)
        assert dist[0, 1] == pytest.approx(0.0, abs=1e-6)
        assert dist[1, 0] == pytest.approx(0.0, abs=1e-6)

    def test_tanimoto_distance_disjoint(self):
        """Completely disjoint feature sets should give distance 1."""
        mat = np.array([[1, 1, 0, 0], [0, 0, 1, 1]], dtype=np.float32)
        dist = _tanimoto_distance_matrix(mat)
        assert dist[0, 1] == pytest.approx(1.0, abs=1e-6)

    def test_tanimoto_distance_partial(self):
        """Partial overlap: A={1,2,3}, B={2,3,4} -> intersection=2, union=4 -> sim=0.5, dist=0.5."""
        mat = np.array([[1, 1, 1, 0], [0, 1, 1, 1]], dtype=np.float32)
        dist = _tanimoto_distance_matrix(mat)
        assert dist[0, 1] == pytest.approx(0.5, abs=1e-6)


class TestKuncheva:
    """Tests for _kuncheva_from_binary."""

    def test_kuncheva_single_model(self):
        """Single model should return 1.0."""
        mat = np.array([[1, 0, 1, 0, 1]], dtype=np.float32)
        result = _kuncheva_from_binary(mat, total_features=10)
        assert result == 1.0

    def test_kuncheva_identical_models(self):
        """Identical models should give Kuncheva index of 1.0."""
        mat = np.array([
            [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
            [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
            [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
        ], dtype=np.float32)
        result = _kuncheva_from_binary(mat, total_features=10)
        assert result == pytest.approx(1.0, abs=1e-6)

    def test_kuncheva_disjoint_models(self):
        """Disjoint feature sets should give a low/negative Kuncheva index."""
        mat = np.array([
            [1, 1, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 1, 1, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 1, 1, 0, 0, 0, 0],
        ], dtype=np.float32)
        result = _kuncheva_from_binary(mat, total_features=10)
        # Disjoint sets with d=2, c=10: (0 - 4/10) / (2*(1-2/10)) = -0.4/1.6 = -0.25
        assert result < 0.0


class TestCwRel:
    """Tests for _cw_rel_from_binary."""

    def test_cw_rel_identical(self):
        """Identical models should give CW_rel of 1.0."""
        mat = np.array([
            [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
            [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
            [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
        ], dtype=np.float32)
        result = _cw_rel_from_binary(mat, total_features=10)
        assert result == pytest.approx(1.0, abs=1e-6)

    def test_cw_rel_single(self):
        """Single model should return 1.0."""
        mat = np.array([[1, 0, 1, 0, 1]], dtype=np.float32)
        result = _cw_rel_from_binary(mat, total_features=10)
        assert result == 1.0


class TestComputeStabilityAnalysis:
    """Tests for compute_stability_analysis."""

    def test_compute_stability_empty(self):
        """Empty population should produce the empty result structure."""
        result = compute_stability_analysis([], [])
        assert result["stability_by_k"] == []
        assert result["dendrogram"]["labels"] == []
        assert result["feature_sparsity_heatmap"]["features"] == []
        assert result["stats"]["n_models"] == 0

    def test_compute_stability_basic(self):
        """Population of 5 models with varying k: verify all expected keys are present."""
        feature_names = [f"feat_{i}" for i in range(20)]

        population = [
            _make_population_individual(
                features_dict={},
                named_features={"feat_0": 1, "feat_1": -1, "feat_2": 1},
                k=3, auc=0.90, accuracy=0.85,
            ),
            _make_population_individual(
                features_dict={},
                named_features={"feat_0": 1, "feat_1": -1, "feat_3": 1},
                k=3, auc=0.88, accuracy=0.83,
            ),
            _make_population_individual(
                features_dict={},
                named_features={"feat_0": 1, "feat_4": -1, "feat_5": 1, "feat_6": -1, "feat_7": 1},
                k=5, auc=0.92, accuracy=0.87,
            ),
            _make_population_individual(
                features_dict={},
                named_features={"feat_0": 1, "feat_4": -1, "feat_5": 1, "feat_8": -1, "feat_9": 1},
                k=5, auc=0.91, accuracy=0.86,
            ),
            _make_population_individual(
                features_dict={},
                named_features={"feat_0": 1, "feat_4": -1, "feat_5": 1, "feat_6": -1, "feat_10": 1},
                k=5, auc=0.93, accuracy=0.88,
            ),
        ]

        result = compute_stability_analysis(population, feature_names)

        # Top-level keys
        assert "stability_by_k" in result
        assert "dendrogram" in result
        assert "feature_sparsity_heatmap" in result
        assert "stats" in result

        # stability_by_k should have entries for k=3 and k=5
        k_values = [entry["k"] for entry in result["stability_by_k"]]
        assert 3 in k_values
        assert 5 in k_values

        # Each entry should have the expected keys
        for entry in result["stability_by_k"]:
            assert "kuncheva" in entry
            assert "tanimoto" in entry
            assert "cw_rel" in entry
            assert "mean_auc" in entry
            assert "mean_accuracy" in entry
            assert "n_models" in entry

        # Dendrogram should have labels for all 5 models
        assert len(result["dendrogram"]["labels"]) == 5

        # Feature sparsity heatmap
        heatmap = result["feature_sparsity_heatmap"]
        assert len(heatmap["features"]) > 0
        assert len(heatmap["sparsity_levels"]) == 2  # k=3 and k=5

        # Stats
        assert result["stats"]["n_models"] == 5
        assert result["stats"]["n_features"] == 20
        assert result["stats"]["k_min"] == 3
        assert result["stats"]["k_max"] == 5


class TestFeatureSparsityHeatmap:
    """Tests for _compute_feature_sparsity_heatmap."""

    def test_feature_sparsity_heatmap(self):
        """Verify features are sorted by total prevalence (most prevalent first)."""
        models = [
            _make_model(0, 3, {"f1", "f2", "f3"}),
            _make_model(1, 3, {"f1", "f2", "f4"}),
            _make_model(2, 3, {"f1", "f3", "f5"}),
            _make_model(3, 5, {"f1", "f2", "f3", "f4", "f5"}),
        ]

        heatmap = _compute_feature_sparsity_heatmap(models)

        # f1 appears in all 4 models, so it should be first
        assert heatmap["features"][0] == "f1"

        # f2, f3 appear in 3 models each; both should come before f4 and f5 (2 each)
        top_3 = set(heatmap["features"][:3])
        assert "f1" in top_3

        # All features should be present
        assert set(heatmap["features"]) == {"f1", "f2", "f3", "f4", "f5"}

        # Sparsity levels should be [3, 5]
        assert heatmap["sparsity_levels"] == [3, 5]

        # Values should be a list of lists with correct dimensions
        assert len(heatmap["values"]) == len(heatmap["features"])
        for row in heatmap["values"]:
            assert len(row) == len(heatmap["sparsity_levels"])

        # For f1 at k=3: appears in 3 out of 3 k=3 models -> 1.0
        f1_idx = heatmap["features"].index("f1")
        k3_col_idx = heatmap["sparsity_levels"].index(3)
        assert heatmap["values"][f1_idx][k3_col_idx] == pytest.approx(1.0, abs=0.01)


# ============================================================================
# 2. Prediction service tests
# ============================================================================

def _make_results(data_type: str = "raw", threshold: float = 0.0,
                  feature_names: list | None = None,
                  features: dict | None = None) -> dict:
    """Build a mock results dict for predict_from_model."""
    if feature_names is None:
        feature_names = ["feat_A", "feat_B", "feat_C"]
    if features is None:
        features = {"0": 1.5, "2": -0.8}
    return {
        "feature_names": feature_names,
        "best_individual": {
            "features": features,
            "data_type": data_type,
            "threshold": threshold,
        },
    }


def _make_x_data(n_samples: int = 10, feature_names: list | None = None,
                 features_in_rows: bool = True) -> pd.DataFrame:
    """Build a mock abundance DataFrame.

    If features_in_rows=True, rows are features, columns are samples (TSV convention).
    """
    if feature_names is None:
        feature_names = ["feat_A", "feat_B", "feat_C"]
    rng = np.random.default_rng(42)
    samples = [f"sample_{i}" for i in range(n_samples)]
    if features_in_rows:
        data = rng.random((len(feature_names), n_samples))
        return pd.DataFrame(data, index=feature_names, columns=samples)
    else:
        data = rng.random((n_samples, len(feature_names)))
        return pd.DataFrame(data, index=samples, columns=feature_names)


class TestPredictFromModel:
    """Tests for predict_from_model."""

    def test_predict_basic(self):
        """Basic prediction: verify output has correct keys and dimensions."""
        results = _make_results()
        x_data = _make_x_data()

        out = predict_from_model(results, x_data, features_in_rows=True)

        assert "sample_names" in out
        assert "scores" in out
        assert "predicted_classes" in out
        assert "threshold" in out
        assert "matched_features" in out
        assert "missing_features" in out
        assert "n_samples" in out

        assert out["n_samples"] == 10
        assert len(out["scores"]) == 10
        assert len(out["predicted_classes"]) == 10
        assert all(c in (0, 1) for c in out["predicted_classes"])

    def test_predict_with_labels(self):
        """Include y_labels: verify evaluation metrics are present."""
        results = _make_results(threshold=0.5)
        x_data = _make_x_data()
        sample_names = x_data.columns.tolist()
        y_labels = pd.Series(
            [0, 0, 0, 0, 0, 1, 1, 1, 1, 1],
            index=sample_names,
        )

        out = predict_from_model(results, x_data, y_labels=y_labels, features_in_rows=True)

        assert "evaluation" in out
        eval_metrics = out["evaluation"]
        assert "auc" in eval_metrics
        assert "accuracy" in eval_metrics
        assert "sensitivity" in eval_metrics
        assert "specificity" in eval_metrics
        assert "confusion_matrix" in eval_metrics
        cm = eval_metrics["confusion_matrix"]
        assert cm["tp"] + cm["tn"] + cm["fp"] + cm["fn"] == 10

    def test_predict_missing_features(self):
        """Some model features not in x_data should be listed in missing_features."""
        results = _make_results(
            feature_names=["feat_A", "feat_MISSING", "feat_C"],
            features={"0": 1.0, "1": -0.5, "2": 0.8},
        )
        x_data = _make_x_data(feature_names=["feat_A", "feat_B", "feat_C"])

        out = predict_from_model(results, x_data, features_in_rows=True)

        assert "feat_MISSING" in out["missing_features"]
        assert "feat_A" in out["matched_features"]
        assert "feat_C" in out["matched_features"]

    def test_predict_prevalence_data_type(self):
        """data_type='prevalence' should normalize rows so each sample sums to ~1."""
        results = _make_results(data_type="prevalence", features={"0": 1.0})

        # Create data with known values
        x_data = pd.DataFrame(
            [[10.0, 20.0, 30.0], [5.0, 5.0, 10.0]],
            index=["feat_A", "feat_B"],
            columns=["s0", "s1", "s2"],
        )
        # After transpose: samples in rows, features in cols
        # s0: feat_A=10, feat_B=5 -> sum=15 -> normalized feat_A=10/15
        # Score for s0 = (10/15) * 1.0 = 0.6667

        out = predict_from_model(
            {"feature_names": ["feat_A", "feat_B"],
             "best_individual": {"features": {"0": 1.0}, "data_type": "prevalence", "threshold": 0.0}},
            x_data, features_in_rows=True,
        )

        # s0: feat_A=10, feat_B=5, sum=15, normalized_feat_A = 10/15 ~ 0.6667
        assert out["scores"][0] == pytest.approx(10.0 / 15.0, abs=1e-4)


class TestComputeAuc:
    """Tests for _compute_auc."""

    def test_compute_auc_perfect(self):
        """Perfect separation: all positives scored higher than negatives -> AUC ~1.0."""
        y_true = np.array([0, 0, 0, 1, 1, 1], dtype=float)
        scores = np.array([0.1, 0.2, 0.3, 0.7, 0.8, 0.9])
        auc = _compute_auc(y_true, scores)
        assert auc == pytest.approx(1.0, abs=1e-6)

    def test_compute_auc_random(self):
        """Random labels and scores: AUC should be close to 0.5 for large sample."""
        rng = np.random.default_rng(123)
        n = 10000
        y_true = rng.choice([0.0, 1.0], size=n)
        scores = rng.random(n)
        auc = _compute_auc(y_true, scores)
        assert auc == pytest.approx(0.5, abs=0.05)

    def test_compute_auc_no_positives(self):
        """Edge case with no positive labels -> returns 0.5."""
        y_true = np.array([0.0, 0.0, 0.0])
        scores = np.array([0.1, 0.5, 0.9])
        auc = _compute_auc(y_true, scores)
        assert auc == 0.5


class TestParseTsv:
    """Tests for parse_tsv."""

    def test_parse_tsv(self):
        """Parse TSV bytes into a DataFrame."""
        content = b"id\tsample1\tsample2\nfeat1\t1.0\t2.0\nfeat2\t3.0\t4.0\n"
        df = parse_tsv(content)

        assert isinstance(df, pd.DataFrame)
        assert df.shape == (2, 2)
        assert list(df.columns) == ["sample1", "sample2"]
        assert list(df.index) == ["feat1", "feat2"]
        assert df.loc["feat1", "sample1"] == 1.0
        assert df.loc["feat2", "sample2"] == 4.0


# ============================================================================
# 3. Coabundance service tests
# ============================================================================

class TestDetectCommunities:
    """Tests for _detect_communities."""

    def test_detect_communities_louvain(self):
        """Louvain method on a small graph should detect at least 1 community."""
        G = _small_graph()
        communities = _detect_communities(G, method="louvain", seed=42)

        assert len(communities) >= 1
        # All nodes should be covered
        all_nodes = set()
        for comm in communities:
            all_nodes.update(comm)
        assert all_nodes == set(G.nodes())

    def test_detect_communities_greedy(self):
        """Greedy modularity method on a small graph."""
        G = _small_graph()
        communities = _detect_communities(G, method="greedy", seed=42)

        assert len(communities) >= 1
        all_nodes = set()
        for comm in communities:
            all_nodes.update(comm)
        assert all_nodes == set(G.nodes())

    def test_detect_communities_label_propagation(self):
        """Label propagation method on a small graph."""
        G = _small_graph()
        communities = _detect_communities(G, method="label_propagation", seed=42)

        assert len(communities) >= 1
        all_nodes = set()
        for comm in communities:
            all_nodes.update(comm)
        assert all_nodes == set(G.nodes())

    def test_detect_communities_unknown_fallback(self):
        """Unknown method should fall back to Louvain."""
        G = _small_graph()
        communities = _detect_communities(G, method="nonexistent_method", seed=42)

        assert len(communities) >= 1
        all_nodes = set()
        for comm in communities:
            all_nodes.update(comm)
        assert all_nodes == set(G.nodes())


class TestCacheOperations:
    """Tests for _get_cached / _set_cached."""

    def setup_method(self):
        """Clear the cache before each test."""
        _cache.clear()

    def test_cache_operations(self):
        """Set and get from cache, verify hit and miss."""
        key = ("path_x", "path_y", 30.0, 0.3, "all", "", "louvain")
        value = {"nodes": [], "edges": [], "stats": {}}

        # Cache miss
        assert _get_cached(key) is None

        # Cache hit after set
        _set_cached(key, value)
        cached = _get_cached(key)
        assert cached is not None
        assert cached == value

    def test_cache_ttl(self):
        """Expired cache entries should return None (simulated by manipulating timestamp)."""
        key = ("x", "y", 30.0, 0.3, "all", "", "louvain")
        value = {"result": True}

        # Insert with an expired timestamp
        _cache[key] = (time.time() - 700, value)  # 700s > 600s TTL

        # Should return None because it is expired
        assert _get_cached(key) is None


class TestCacheKey:
    """Tests for _cache_key."""

    def test_cache_key(self):
        """Different parameters should produce different keys."""
        key1 = _cache_key("x1.tsv", "y1.tsv", 30.0, 0.3, "all", "f1,f2", "louvain")
        key2 = _cache_key("x1.tsv", "y1.tsv", 30.0, 0.3, "all", "f1,f2", "greedy")
        key3 = _cache_key("x2.tsv", "y1.tsv", 30.0, 0.3, "all", "f1,f2", "louvain")
        key4 = _cache_key("x1.tsv", "y1.tsv", 30.0, 0.3, "all", "f1,f2", "louvain")

        assert key1 != key2  # different community method
        assert key1 != key3  # different x_path
        assert key1 == key4  # same parameters


class TestFbmAnnotation:
    """Tests for _compute_fbm_annotation."""

    def test_fbm_annotation_basic(self):
        """Mock population data: correct prevalence and coefficient."""
        job_results = {
            "population": [
                {"named_features": {"feat_A": 1, "feat_B": -1}},
                {"named_features": {"feat_A": 1, "feat_C": 1}},
                {"named_features": {"feat_A": -1, "feat_B": -1, "feat_C": -1}},
            ],
        }
        feature_ids = ["feat_A", "feat_B", "feat_C", "feat_D"]

        result = _compute_fbm_annotation(job_results, feature_ids)

        # feat_A appears in 3/3 models -> prevalence 1.0
        assert result["feat_A"]["prevalence"] == pytest.approx(1.0, abs=1e-4)
        # feat_A coefficients: +1, +1, -1 -> sum=1 > 0 -> coefficient=1
        assert result["feat_A"]["coefficient"] == 1

        # feat_B appears in 2/3 models -> prevalence ~0.6667
        assert result["feat_B"]["prevalence"] == pytest.approx(2 / 3, abs=1e-4)
        # feat_B coefficients: -1, -1 -> sum=-2 < 0 -> coefficient=-1
        assert result["feat_B"]["coefficient"] == -1

        # feat_C appears in 2/3 models
        assert result["feat_C"]["prevalence"] == pytest.approx(2 / 3, abs=1e-4)

        # feat_D not in any model -> not in result
        assert "feat_D" not in result

    def test_fbm_annotation_empty(self):
        """Empty population -> empty result."""
        result = _compute_fbm_annotation({"population": []}, ["feat_A"])
        assert result == {}

        result2 = _compute_fbm_annotation({}, ["feat_A"])
        assert result2 == {}


class TestEmptyResult:
    """Tests for _empty_result."""

    def test_empty_result(self):
        """Verify the empty result structure has all expected keys and values."""
        result = _empty_result(100, 50)

        assert result["nodes"] == []
        assert result["edges"] == []
        assert result["modules"] == []
        assert result["taxonomy_legend"] == []

        stats = result["stats"]
        assert stats["n_features_total"] == 100
        assert stats["n_features_filtered"] == 50
        assert stats["n_nodes"] == 0
        assert stats["n_edges"] == 0
        assert stats["n_modules"] == 0
        assert stats["modularity"] == 0.0

    def test_empty_result_defaults(self):
        """_empty_result with no arguments should use 0 defaults."""
        result = _empty_result()
        assert result["stats"]["n_features_total"] == 0
        assert result["stats"]["n_features_filtered"] == 0
