"""Data Explore / annotation fixes (audit findings BE-F9, F10, F13, F17, F18, F1)."""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from app.services import coabundance, data_analysis, matrix_io, msp_annotations
from app.routers import data_explore


def _dataset(tmp_path, samples_in_rows=False, n=40, shuffle_y=True):
    rng = np.random.default_rng(5)
    samples = [f"s{i:02d}" for i in range(n)]
    y = np.array([i % 2 for i in range(n)])
    X = pd.DataFrame(
        {f"f{j}": rng.random(n) * (1 + (j == 0) * y) for j in range(6)}, index=samples,
    )
    x_path = tmp_path / ("X_rows.tsv" if samples_in_rows else "X.tsv")
    (X if samples_in_rows else X.T).to_csv(x_path, sep="\t", index_label="id")
    ydf = pd.DataFrame({"class": y}, index=samples)
    if shuffle_y:
        ydf = ydf.sample(frac=1.0, random_state=2)
    y_path = tmp_path / "y.tsv"
    ydf.to_csv(y_path, sep="\t", index_label="id")
    return str(x_path), str(y_path), X, pd.Series(y, index=samples)


class TestMatrixLoader:
    def test_labels_are_matched_by_name(self, tmp_path):
        x, y, X, y_true = _dataset(tmp_path)
        Xl, yl = matrix_io.load_xy(x, y, True)
        assert list(Xl.index) == list(X.index)
        assert (yl.to_numpy() == y_true.to_numpy()).all()

    def test_orientation_is_detected(self, tmp_path):
        x, y, _, _ = _dataset(tmp_path, samples_in_rows=False)
        assert matrix_io.detect_features_in_rows(x, y) is True
        x2, y2, _, _ = _dataset(tmp_path, samples_in_rows=True)
        assert matrix_io.detect_features_in_rows(x2, y2) is False

    def test_both_orientations_give_the_same_statistics(self, tmp_path):
        x, y, _, _ = _dataset(tmp_path, samples_in_rows=False)
        x2, _, _, _ = _dataset(tmp_path, samples_in_rows=True)
        a = data_analysis.compute_feature_abundance(x, y, ["f0", "f3"], features_in_rows=True)
        b = data_analysis.compute_feature_abundance(x2, y, ["f0", "f3"], features_in_rows=False)
        assert a == b and len(a) == 2
        assert a[0]["classes"]["1"]["mean"] > a[0]["classes"]["0"]["mean"]

    def test_wrong_orientation_is_reported_not_computed(self, tmp_path):
        x2, y2, _, _ = _dataset(tmp_path, samples_in_rows=True)
        with pytest.raises(ValueError, match="orientation"):
            data_analysis.compute_feature_abundance(x2, y2, ["f0"], features_in_rows=True)

    def test_cache_follows_file_changes(self, tmp_path):
        x, y, X, _ = _dataset(tmp_path)
        first = matrix_io.load_matrix(x, True)
        assert matrix_io.load_matrix(x, True) is first          # cached
        (X.T * 2).to_csv(x, sep="\t", index_label="id")
        second = matrix_io.load_matrix(x, True)
        assert second is not first
        assert second.iloc[0, 0] == pytest.approx(X.iloc[0, 0] * 2)

    def test_continuous_labels_are_rejected_for_class_views(self, tmp_path):
        with pytest.raises(ValueError):
            matrix_io.class_codes(pd.Series([0.2, 1.7, 3.1]))


class TestFilteringCache:
    def test_key_includes_every_argument(self):
        base = data_analysis._cache_key("x", "y", "wilcoxon", 10.0, 0.05, 0.0, True)
        assert base != data_analysis._cache_key("x", "y", "wilcoxon", 10.0, 0.05, 0.001, True)
        assert base != data_analysis._cache_key("x", "y", "wilcoxon", 10.0, 0.05, 0.0, False)
        assert base == data_analysis._cache_key("x", "y", "wilcoxon", 10.0, 0.05, 0.0, True)

    def test_min_feature_value_is_not_served_from_a_stale_entry(self, tmp_path, monkeypatch):
        """Changing 'min feature value' used to return the previous result for 5 minutes."""
        x, y, _, _ = _dataset(tmp_path)
        calls = []
        monkeypatch.setattr(data_analysis, "HAS_ENGINE", False)
        monkeypatch.setattr(data_analysis, "_mock_filtering", lambda m: calls.append(1) or {"n": len(calls)})
        data_analysis._cache.clear()
        a = data_analysis.run_filtering(x, y, min_feature_value=0.0)
        b = data_analysis.run_filtering(x, y, min_feature_value=0.5)
        c = data_analysis.run_filtering(x, y, min_feature_value=0.0)
        assert a != b and a == c and len(calls) == 2


class TestDistances:
    @pytest.mark.parametrize("metric", ["braycurtis", "jaccard"])
    @pytest.mark.parametrize("transform", ["log", "zscore"])
    def test_undefined_combinations_are_rejected(self, tmp_path, metric, transform):
        x, y, _, _ = _dataset(tmp_path)
        with pytest.raises(ValueError, match="not defined"):
            data_analysis.compute_pcoa(x, y, metric=metric, transform=transform, n_permutations=9)

    def test_valid_combinations_still_work(self, tmp_path):
        x, y, _, _ = _dataset(tmp_path)
        raw = data_analysis.compute_pcoa(x, y, metric="braycurtis", transform="raw", n_permutations=9)
        z = data_analysis.compute_pcoa(x, y, metric="euclidean", transform="zscore", n_permutations=9)
        for res in (raw, z):
            assert res["n_samples"] == 40
            assert np.isfinite(np.array(res["coords"])).all()
            assert 0 < res["permanova"]["p_value"] <= 1


class TestSpearman:
    def test_vectorised_matrix_equals_scipy(self):
        rng = np.random.default_rng(9)
        mat = rng.integers(0, 6, size=(60, 12)).astype(float)   # many ties
        rho, pval = coabundance.spearman_matrix(mat)
        ref_rho, ref_p = stats.spearmanr(mat, axis=0)
        np.testing.assert_allclose(rho, ref_rho, atol=1e-10)
        off = ~np.eye(12, dtype=bool)
        np.testing.assert_allclose(pval[off], ref_p[off], atol=1e-10)

    def test_network_is_identical_above_the_old_loop_threshold(self, tmp_path, monkeypatch):
        """>1000 features used to go through a Python double loop; same edges, no loop."""
        monkeypatch.setattr(msp_annotations, "get_annotations", lambda names: {})
        rng = np.random.default_rng(4)
        n, p = 30, 1100
        base = rng.random((n, 3))
        data = np.column_stack([base[:, j % 3] + rng.normal(0, 0.05, n) if j < 9 else rng.random(n) for j in range(p)])
        samples = [f"s{i}" for i in range(n)]
        feats = [f"f{j}" for j in range(p)]
        x = tmp_path / "X.tsv"
        pd.DataFrame(data.T, index=feats, columns=samples).to_csv(x, sep="\t", index_label="id")
        y = tmp_path / "y.tsv"
        pd.DataFrame({"class": [i % 2 for i in range(n)]}, index=samples).to_csv(y, sep="\t", index_label="id")
        t0 = time.time()
        net = coabundance.compute_coabundance_network(
            str(x), str(y), min_prevalence_pct=0.0, correlation_threshold=0.9,
        )
        assert time.time() - t0 < 30
        pairs = {(e["source"], e["target"]) for e in net["edges"]}
        assert ("f0", "f3") in pairs and ("f1", "f4") in pairs and ("f0", "f1") not in pairs
        r, _ = stats.spearmanr(data[:, 0], data[:, 3])
        edge = next(e for e in net["edges"] if (e["source"], e["target"]) == ("f0", "f3"))
        assert edge["correlation"] == pytest.approx(round(float(r), 4))


class TestFbmModuleFilter:
    def test_metrics_are_read_from_the_nested_block(self):
        network = {"nodes": [{"id": "a", "module": 0}, {"id": "b", "module": 0}, {"id": "c", "module": 1}]}
        population = [
            {"metrics": {"fit": 0.7, "auc": 0.71, "accuracy": 0.6, "language": "ternary", "data_type": "raw"},
             "named_features": {"a": 1, "b": -1}},
            {"metrics": {"fit": 0.9, "auc": 0.91, "accuracy": 0.8, "language": "binary", "data_type": "prevalence"},
             "named_features": {"a": 1, "b": 1}},
            {"metrics": {"fit": 0.99, "auc": 0.99}, "named_features": {"c": 1}},
        ]
        out = data_explore._score_models_by_module(population, network, [0])
        assert out["filtered_count"] == 2
        best, second = out["filtered_models"]
        # equal coverage: the secondary sort by fit now has something to sort on
        assert (best["fit"], best["auc"], best["language"], best["data_type"]) == (0.9, 0.91, "binary", "prevalence")
        assert second["fit"] == 0.7 and second["accuracy"] == 0.6


class TestMspAnnotations:
    @pytest.fixture(autouse=True)
    def _isolated_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(msp_annotations, "CACHE_FILE", tmp_path / "cache" / "msp.json")
        monkeypatch.setattr(msp_annotations, "_cache", {})

    def test_transient_failures_are_not_cached(self, monkeypatch):
        """An outage used to blank the annotation permanently."""
        calls = []

        def flaky(msp_id):
            calls.append(msp_id)
            return msp_id, (msp_annotations._ERROR if len(calls) == 1 else {"species": "E. coli"})

        monkeypatch.setattr(msp_annotations, "_fetch_single", flaky)
        assert msp_annotations.get_annotations(["msp_0001"]) == {}
        assert "msp_0001" not in msp_annotations._cache
        assert msp_annotations.get_annotations(["msp_0001"]) == {"msp_0001": {"species": "E. coli"}}
        assert len(calls) == 2

    def test_unknown_ids_are_remembered_for_a_while_only(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            msp_annotations, "_fetch_single",
            lambda i: (calls.append(i) or i, msp_annotations._MISS),
        )
        assert msp_annotations.get_annotations(["msp_9999"]) == {}
        assert msp_annotations.get_annotations(["msp_9999"]) == {}
        assert len(calls) == 1                                    # negative-cached
        msp_annotations._cache["msp_9999"]["_miss"] -= msp_annotations.MISS_TTL + 1
        msp_annotations.get_annotations(["msp_9999"])
        assert len(calls) == 2                                    # expired, asked again

    def test_legacy_poisoned_entries_are_refetched(self, monkeypatch):
        msp_annotations._cache["msp_0002"] = {}                   # written by older versions
        monkeypatch.setattr(msp_annotations, "_fetch_single", lambda i: (i, {"species": "B. fragilis"}))
        assert msp_annotations.get_annotations(["msp_0002"])["msp_0002"]["species"] == "B. fragilis"

    def test_taxonomy_suffix_and_bad_input(self, monkeypatch):
        asked = []
        monkeypatch.setattr(
            msp_annotations, "_fetch_single", lambda i: (asked.append(i) or i, {"species": "x"}),
        )
        full = "msp_0074;Bacteria;Bacillota_A;Clostridia"
        out = msp_annotations.get_annotations([full, 42, None, "msp_../etc", "gene_1", {"a": 1}])
        assert asked == ["msp_0074"]
        assert list(out) == [full]

    def test_cache_file_is_written_atomically_and_reloaded(self, monkeypatch):
        monkeypatch.setattr(msp_annotations, "_fetch_single", lambda i: (i, {"species": "x"}))
        msp_annotations.get_annotations(["msp_0003"])
        assert msp_annotations.CACHE_FILE.exists()
        assert not list(msp_annotations.CACHE_FILE.parent.glob("*.tmp"))
        monkeypatch.setattr(msp_annotations, "_cache", None)
        assert msp_annotations._load_cache()["msp_0003"] == {"species": "x"}


# ---------------------------------------------------------------------------
# The event loop stays free while analyses run (audit finding BE-F1)
# ---------------------------------------------------------------------------

from tests.test_api import (  # noqa: E402,F401 - fixtures and helpers
    db_session, client, auth_client, clean_data, _create_project_with_datasets,
)


class TestEventLoopStaysResponsive:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,target", [
        ("/api/data-explore/{pid}/ordination?method=pcoa", "compute_pcoa"),
        ("/api/data-explore/{pid}/feature-stats", "run_filtering"),
        ("/api/data-explore/{pid}/aberrant-correlations", "compute_aberrant_correlations"),
    ])
    async def test_slow_analysis_does_not_block_other_requests(self, auth_client, monkeypatch, path, target):
        import asyncio

        pid, _, _ = await _create_project_with_datasets(auth_client)

        def _slow(*args, **kwargs):
            time.sleep(1.0)                       # blocking, like the real computation
            return {"features": [], "selected_count": 0, "method": "x", "n_features": 0, "pairs": []}

        monkeypatch.setattr(data_analysis, target, _slow)
        loop = asyncio.get_running_loop()
        ticks = []

        async def _heartbeat():
            # If the handler ran on the event loop, no tick could happen during the sleep.
            t_end = loop.time() + 0.9
            while loop.time() < t_end:
                ticks.append(loop.time())
                await asyncio.sleep(0.05)

        resp, _ = await asyncio.gather(auth_client.get(path.format(pid=pid)), _heartbeat())
        assert resp.status_code == 200, resp.text
        assert len(ticks) >= 10
        assert max(b - a for a, b in zip(ticks, ticks[1:])) < 0.5

    @pytest.mark.asyncio
    async def test_undefined_distance_is_a_400_not_a_500(self, auth_client):
        pid, _, _ = await _create_project_with_datasets(auth_client)
        resp = await auth_client.get(
            f"/api/data-explore/{pid}/ordination", params={"metric": "braycurtis", "transform": "zscore"},
        )
        assert resp.status_code == 400
        assert "not defined" in json_message(resp)

    @pytest.mark.asyncio
    async def test_typed_bodies_reject_bad_input(self, auth_client):
        pid, _, _ = await _create_project_with_datasets(auth_client)
        bad = await auth_client.post(
            f"/api/data-explore/{pid}/fbm-module-filter", json={"job_id": "abc", "module_ids": ["x", "y"]},
        )
        assert bad.status_code == 422                 # used to be a silent empty result
        bad2 = await auth_client.post("/api/data-explore/msp-annotations", json={"features": "msp_0001"})
        assert bad2.status_code == 422
        ok = await auth_client.post("/api/data-explore/msp-annotations", json={"features": ["gene_1", "otu_2"]})
        assert ok.status_code == 200 and ok.json() == {"annotations": {}}


def json_message(resp) -> str:
    body = resp.json()
    if isinstance(body.get("error"), dict):
        return str(body["error"].get("message", ""))
    return str(body.get("detail", ""))
