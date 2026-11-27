"""OR (clause) languages of gpredomics in the web app.

A clause model (binary-or, ternary-or, ratio-or) replaces each feature of a
classic BTR model by a positive disjunctive clause scored by the max of its
features. The engine produces them with Beam only. These tests cover the
scoring port, the results format, the run configuration, the mock engine and
the exports; the engine itself is tested in gpredomics.
"""

from __future__ import annotations

import csv
import io

import numpy as np
import pandas as pd
import pytest
import yaml
from pydantic import ValidationError

from app.models.schemas import RunConfig, or_languages_in
# Shared API fixtures live in test_api.py (importing them registers them here).
from tests.test_api import auth_client, clean_data, client, db_session  # noqa: F401
from app.services import engine as ml_engine
from app.services import worker
from app.services.model_format import format_model_formula, model_terms
from app.services.prediction import (
    UnsupportedModelError,
    base_language,
    clause_columns,
    is_or_language,
    normalize_language,
    predict_from_model,
    score_matrix,
)


# ---------------------------------------------------------------------------
# Language names
# ---------------------------------------------------------------------------

class TestLanguageNames:
    @pytest.mark.parametrize("alias,expected", [
        ("ter-or", "ternary-or"), ("Ternary-OR", "ternary-or"), ("1-or", "ternary-or"),
        ("bin-or", "binary-or"), ("binary_or", "binary-or"),
        ("ratio-or", "ratio-or"), ("3-or", "ratio-or"),
    ])
    def test_aliases(self, alias, expected):
        assert normalize_language(alias) == expected
        assert is_or_language(alias)
        assert base_language(alias) == expected.replace("-or", "")

    def test_classic_languages_are_not_or(self):
        for lang in ("bin", "ternary", "pow2", "ratio"):
            assert not is_or_language(lang)
            assert base_language(lang) == normalize_language(lang)

    def test_pow2_or_is_not_scorable(self):
        with pytest.raises(UnsupportedModelError):
            normalize_language("pow2-or")
        assert not is_or_language("pow2-or")

    def test_or_languages_in_config_value(self):
        assert or_languages_in("bin, ter-or ,ratio-or") == ["ter-or", "ratio-or"]
        assert or_languages_in("bin,ter,ratio") == []
        assert or_languages_in(None) == []


# ---------------------------------------------------------------------------
# Scoring (mirrors Individual::evaluate_or_with)
# ---------------------------------------------------------------------------

class TestClauseScoring:
    # columns: a, b, c, d
    X = np.array([
        [0.0, 0.5, 0.2, 0.0],
        [0.3, 0.0, 0.0, 0.7],
        [0.9, 0.8, 0.1, 0.1],
        [0.0, 0.0, 0.0, 0.0],
    ])

    def test_ternary_or_raw_is_max_per_clause(self):
        # (a ∨ b) + c - d
        s = score_matrix(self.X, [1, 1, 1, -1], "ternary-or", "raw", clauses=[[0, 1], [2], [3]])
        expected = np.maximum(self.X[:, 0], self.X[:, 1]) + self.X[:, 2] - self.X[:, 3]
        np.testing.assert_allclose(s, expected)

    def test_prevalence_is_boolean_or(self):
        # (a ∨ b)⁰ - (c ∨ d)⁰ with epsilon 1e-5
        s = score_matrix(self.X, [1, 1, -1, -1], "ter-or", "prev", clauses=[[0, 1], [2, 3]])
        assert s.tolist() == [1.0 - 1.0, 1.0 - 1.0, 1.0 - 1.0, 0.0]

    def test_binary_or_counts_true_clauses(self):
        s = score_matrix(self.X[:, :3], [1, 1, 1], "bin-or", "prev", clauses=[[0, 1], [2]])
        assert s.tolist() == [2.0, 1.0, 2.0, 0.0]

    def test_ratio_or(self):
        eps = 1e-5
        s = score_matrix(self.X, [1, 1, -1, -1], "ratio-or", "raw", epsilon=eps, clauses=[[0, 1], [2, 3]])
        num = np.maximum(self.X[:, 0], self.X[:, 1])
        den = np.maximum(self.X[:, 2], self.X[:, 3])
        np.testing.assert_allclose(s, num / (den + eps))

    def test_log_absent_values_contribute_zero(self):
        eps = 0.1
        s = score_matrix(self.X, [1, 1, -1, -1], "ternary-or", "log", epsilon=eps, clauses=[[0, 1], [2, 3]])
        t = np.where(self.X != 0, np.log(np.where(self.X != 0, self.X, 1.0) / eps), 0.0)
        expected = np.maximum(t[:, 0], t[:, 1]) - np.maximum(t[:, 2], t[:, 3])
        np.testing.assert_allclose(s, expected)

    def test_singleton_clauses_equal_the_classic_model(self):
        coefs = [1, -1, 1, -1]
        for dtype in ("raw", "prev", "log"):
            classic = score_matrix(self.X, coefs, "ternary", dtype)
            singles = score_matrix(self.X, coefs, "ternary-or", dtype, clauses=[[0], [1], [2], [3]])
            none = score_matrix(self.X, coefs, "ternary-or", dtype)
            np.testing.assert_allclose(singles, classic)
            np.testing.assert_allclose(none, classic)

    def test_zero_coefficient_clause_is_ignored(self):
        s = score_matrix(self.X, [0, 0, 1, 0], "ternary-or", "raw", clauses=[[0, 1], [2], [3]])
        np.testing.assert_allclose(s, self.X[:, 2])

    def test_clause_columns_maps_indices_to_positions(self):
        assert clause_columns([[12, 3], [40]], [3, 12, 40]) == [[1, 0], [2]]
        # unknown features are dropped, empty clauses vanish
        assert clause_columns([[99], [3]], [3, 12]) == [[0]]
        assert clause_columns(None, [3]) == []


class TestPredictFromModel:
    @staticmethod
    def _results(language="ternary-or", clauses=None):
        return {
            "feature_names": ["fa", "fb", "fc", "fd"],
            "epsilon": 1e-5,
            "best_individual": {
                "language": language, "data_type": "raw", "threshold": 0.5,
                "features": {"0": 1, "1": 1, "2": -1},
                **({"clauses": clauses} if clauses is not None else {}),
            },
        }

    @staticmethod
    def _x():
        # features in rows (gpredomics convention), two samples
        return pd.DataFrame({"s1": [0.2, 0.9, 0.1, 5.0], "s2": [0.0, 0.0, 0.4, 5.0]},
                            index=["fa", "fb", "fc", "fd"])

    def test_scores_use_the_clauses(self):
        out = predict_from_model(self._results(clauses=[[0, 1], [2]]), self._x(), features_in_rows=True)
        assert out["language"] == "ternary-or"
        assert out["scores"] == pytest.approx([max(0.2, 0.9) - 0.1, 0.0 - 0.4])
        assert out["predicted_classes"] == [1, 0]

    def test_without_clauses_falls_back_to_the_base_language(self):
        out = predict_from_model(self._results(), self._x(), features_in_rows=True)
        assert out["scores"] == pytest.approx([0.2 + 0.9 - 0.1, -0.4])

    def test_classic_model_ignores_a_stray_clauses_key(self):
        out = predict_from_model(self._results("ternary", clauses=[[0, 1], [2]]), self._x(), features_in_rows=True)
        assert out["scores"] == pytest.approx([0.2 + 0.9 - 0.1, -0.4])


# ---------------------------------------------------------------------------
# Worker: results format
# ---------------------------------------------------------------------------

class _FakeIndividual:
    def __init__(self, features, clauses=None, language="ternary-or", data_type="raw"):
        self._features = features
        self._clauses = clauses
        self._metrics = {"language": language, "data_type": data_type}

    def get_features(self):
        return dict(self._features)

    def get_metrics(self):
        return dict(self._metrics)

    def get_clauses(self):
        return self._clauses


class _OldIndividual:
    """Bindings without get_clauses (classic models only)."""

    def __init__(self, features):
        self._features = features

    def get_features(self):
        return dict(self._features)

    def get_metrics(self):
        return {"language": "ternary", "data_type": "raw"}


class TestWorkerClauses:
    def test_model_clauses(self):
        assert worker._model_clauses(_FakeIndividual({0: 1}, [[0]])) == [[0]]
        assert worker._model_clauses(_FakeIndividual({0: 1}, None)) is None
        assert worker._model_clauses(_FakeIndividual({0: 1}, [])) is None
        assert worker._model_clauses(_OldIndividual({0: 1})) is None

    def test_named_clauses_carry_one_coefficient_each(self):
        named = worker._named_clauses([[0, 2], [1]], {0: 1, 2: 1, 1: -1}, ["a", "b", "c"])
        assert named == [{"coef": 1, "features": ["a", "c"]}, {"coef": -1, "features": ["b"]}]

    def test_named_clauses_drop_unknown_features(self):
        assert worker._named_clauses([[7], [0]], {0: 1, 7: 1}, ["a"]) == [{"coef": 1, "features": ["a"]}]

    def test_score_individual_uses_clauses(self):
        ctx = {
            "feature_names": ["a", "b", "c"],
            "x": np.array([[0.1, 0.8, 0.3], [0.0, 0.0, 0.5]]),
            "epsilon": 1e-5, "zstats": {},
        }
        ind = _FakeIndividual({0: 1, 1: 1, 2: -1}, [[0, 1], [2]])
        np.testing.assert_allclose(worker._score_individual(ind, ctx), [0.8 - 0.3, -0.5])
        old = _OldIndividual({0: 1, 1: 1, 2: -1})
        np.testing.assert_allclose(worker._score_individual(old, ctx), [0.1 + 0.8 - 0.3, -0.5])


# ---------------------------------------------------------------------------
# Run configuration
# ---------------------------------------------------------------------------

class TestRunConfig:
    def test_or_language_requires_beam(self):
        with pytest.raises(ValidationError, match="Beam"):
            RunConfig.model_validate({"general": {"algo": "ga", "language": "bin,ter-or"}})

    def test_or_language_with_beam_is_accepted(self):
        cfg = RunConfig.model_validate({"general": {"algo": "beam", "language": "ter,ter-or,ratio-or"},
                                        "beam": {"max_clause_size": 2}})
        assert cfg.beam.max_clause_size == 2

    def test_pow2_or_is_refused(self):
        with pytest.raises(ValidationError, match="not implemented"):
            RunConfig.model_validate({"general": {"algo": "beam", "language": "pow2-or"}})

    def test_classic_languages_unchanged(self):
        RunConfig.model_validate({"general": {"algo": "ga", "language": "bin,ter,ratio"}})

    def test_max_clause_size_default_and_bounds(self):
        assert RunConfig().beam.max_clause_size == 3
        with pytest.raises(ValidationError):
            RunConfig.model_validate({"beam": {"max_clause_size": -1}})

    def test_param_yaml_carries_max_clause_size(self, tmp_path):
        cfg = {"general": {"algo": "beam", "language": "ter-or"}, "beam": {"max_clause_size": 2}}
        path = ml_engine.write_param_yaml(cfg, "X.tsv", "y.tsv", "", "", output_dir=str(tmp_path))
        with open(path) as f:
            param = yaml.safe_load(f)
        assert param["beam"]["max_clause_size"] == 2
        assert param["general"]["language"] == "ter-or"

    def test_param_yaml_default_max_clause_size(self, tmp_path):
        path = ml_engine.write_param_yaml({"general": {"algo": "beam"}}, "X.tsv", "y.tsv", "", "",
                                          output_dir=str(tmp_path))
        with open(path) as f:
            assert yaml.safe_load(f)["beam"]["max_clause_size"] == 3

    @pytest.mark.asyncio
    async def test_run_endpoint_rejects_or_language_with_ga(self, auth_client):  # noqa: F811
        from tests.test_api import _create_project_with_datasets

        pid, x_id, y_id = await _create_project_with_datasets(auth_client)
        config = {"general": {"algo": "ga", "language": "ter-or", "data_type": "prev"}}
        resp = await auth_client.post(f"/api/analysis/{pid}/run", json=config,
                                      params={"x_file_id": x_id, "y_file_id": y_id})
        assert resp.status_code == 422
        assert "Beam" in resp.text


# ---------------------------------------------------------------------------
# Formula formatting
# ---------------------------------------------------------------------------

class TestModelFormula:
    def test_ternary_or_prevalence(self):
        model = {
            "language": "ternary-or", "data_type": "prev", "threshold": 0.0,
            "named_clauses": [{"coef": 1, "features": ["A", "B"]}, {"coef": 1, "features": ["C"]},
                              {"coef": -1, "features": ["D", "E"]}],
        }
        assert format_model_formula(model) == "((A⁰ ∨ B⁰) + C⁰) - (D⁰ ∨ E⁰)"
        assert format_model_formula(model, with_threshold=True).endswith(" ≥ 0")

    def test_from_indices_and_clauses(self):
        model = {"metrics": {"language": "binary-or", "data_type": "raw"},
                 "features": {"3": 1, "0": 1, "7": 1}, "clauses": [[0, 3], [7]]}
        assert format_model_formula(model, ["a", "b", "c", "d", "e", "f", "g", "h"]) == "(a ∨ d) + h"

    def test_ratio_or(self):
        model = {"language": "ratio-or", "data_type": "raw",
                 "named_clauses": [{"coef": 1, "features": ["A", "B"]}, {"coef": -1, "features": ["C"]}]}
        assert format_model_formula(model) == "(A ∨ B) / (C + ε)"

    def test_classic_models(self):
        ter = {"language": "ternary", "data_type": "log", "features": {"1": -1, "0": 1}}
        assert format_model_formula(ter, ["A", "B"]) == "ln(A) - ln(B)"
        pow2 = {"language": "pow2", "data_type": "raw", "named_features": {"A": 2, "B": -4, "C": 1}}
        assert format_model_formula(pow2) == "(2*A + C) - 4*B"
        ratio = {"language": "ratio", "data_type": "raw", "named_features": {"A": 1, "B": -1, "C": -1}}
        assert format_model_formula(ratio) == "A / (B + C + ε)"
        binary = {"metrics": {"language": "binary", "data_type": "raw"}, "named_features": {"B": 1, "A": 1}}
        assert format_model_formula(binary) == "A + B"
        assert format_model_formula({"language": "ternary"}) == ""

    def test_terms_order_follows_feature_index(self):
        model = {"features": {"10": -1, "2": 1}, "language": "ternary"}
        names = [f"f{i}" for i in range(11)]
        assert model_terms(model, names) == [{"features": ["f2"], "coef": 1}, {"features": ["f10"], "coef": -1}]


# ---------------------------------------------------------------------------
# Mock engine and exports
# ---------------------------------------------------------------------------

class TestMockAndExports:
    def test_mock_results_include_consistent_or_models(self):
        mock = ml_engine._mock_results()
        or_models = [m for m in mock["population"] if m.get("clauses")]
        assert len(or_models) >= 1
        for m in or_models:
            assert m["metrics"]["language"].endswith("-or")
            flat = sorted(f for c in m["clauses"] for f in c)
            assert flat == sorted(int(i) for i in m["features"])
            assert len(m["named_clauses"]) == len(m["clauses"])
            for clause, named in zip(m["clauses"], m["named_clauses"], strict=True):
                assert {m["features"][str(f)] for f in clause} == {named["coef"]}
                assert named["features"] == [f"feature_{f}" for f in clause]
        assert mock["population_size"] == len(mock["population"])

    @pytest.mark.asyncio
    async def test_exports_show_clauses(self, auth_client, db_session):  # noqa: F811
        from sqlalchemy import text

        from app.services import storage
        from tests.test_api import _create_project_with_datasets, _run_mock_analysis

        pid, x_id, y_id = await _create_project_with_datasets(auth_client)
        job_id = await _run_mock_analysis(auth_client, pid, x_id, y_id)
        mock = ml_engine._mock_results()
        mock["best_individual"].update({
            "language": "ternary-or", "data_type": "prev",
            "features": {"5": 1, "12": -1, "37": 1}, "clauses": [[5, 37], [12]],
        })
        storage.save_job_result(pid, job_id, mock)
        await db_session.execute(text("UPDATE jobs SET status = 'completed' WHERE id = :jid"), {"jid": job_id})
        await db_session.commit()

        resp = await auth_client.get(f"/api/export/{pid}/jobs/{job_id}/csv", params={"section": "best_model"})
        assert resp.status_code == 200
        rows = list(csv.reader(io.StringIO(resp.text)))
        formula = next(r for r in rows if r and r[0] == "formula")[1]
        assert formula == "(feature_5⁰ ∨ feature_37⁰) - feature_12⁰"
        header = rows.index(["Feature", "Coefficient", "Clause"])
        assert rows[header + 1:header + 4] == [["feature_5", "1", "1"], ["feature_37", "1", "1"], ["feature_12", "-1", "2"]]

        resp = await auth_client.get(f"/api/export/{pid}/jobs/{job_id}/csv", params={"section": "population"})
        assert resp.status_code == 200
        rows = list(csv.reader(io.StringIO(resp.text)))
        assert rows[0][-1] == "Formula"
        assert any("∨" in r[-1] for r in rows[1:])

        resp = await auth_client.get(f"/api/export/{pid}/jobs/{job_id}/report")
        assert resp.status_code == 200
        assert "feature_5 ∨ feature_37 (+1)" in resp.text
        assert "model-formula" in resp.text

        resp = await auth_client.get(f"/api/export/{pid}/jobs/{job_id}/pdf")
        assert resp.status_code == 200
        assert resp.content[:5] == b"%PDF-"

    @pytest.mark.asyncio
    async def test_classic_exports_unchanged(self, auth_client, db_session):  # noqa: F811
        from sqlalchemy import text

        from app.services import storage
        from tests.test_api import _create_project_with_datasets, _run_mock_analysis

        pid, x_id, y_id = await _create_project_with_datasets(auth_client)
        job_id = await _run_mock_analysis(auth_client, pid, x_id, y_id)
        storage.save_job_result(pid, job_id, ml_engine._mock_results())
        await db_session.execute(text("UPDATE jobs SET status = 'completed' WHERE id = :jid"), {"jid": job_id})
        await db_session.commit()

        resp = await auth_client.get(f"/api/export/{pid}/jobs/{job_id}/csv", params={"section": "best_model"})
        rows = list(csv.reader(io.StringIO(resp.text)))
        formula = next(r for r in rows if r and r[0] == "formula")[1]
        assert formula == "(feature_5 + feature_37) - feature_12"
        header = rows.index(["Feature", "Coefficient", "Clause"])
        assert [r[2] for r in rows[header + 1:header + 4]] == ["1", "2", "3"]
