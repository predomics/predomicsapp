"""Model scoring must agree with the gpredomics engine (audit findings BE-F4, BE-F5).

The engine comparison runs real (tiny) fits on samples/qin2014_cirrhosis and is
skipped when gpredomicspy or the sample data is not available.
"""

from __future__ import annotations

import itertools
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.services import engine, matrix_io
from app.services.prediction import (
    UnsupportedModelError,
    compute_auc,
    predict_from_model,
    score_matrix,
    zscore_stats,
)

_SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "qin2014_cirrhosis"
_HAVE_DATA = (_SAMPLE / "Xtrain.tsv").exists()


# ---------------------------------------------------------------------------
# AUC: ties
# ---------------------------------------------------------------------------

class TestAucTies:
    def test_all_scores_equal_is_half(self):
        y = np.array([1, 0, 1, 0, 0, 1], dtype=float)
        assert compute_auc(y, np.zeros(6)) == 0.5

    def test_does_not_depend_on_row_order(self):
        # integer-valued scores (binary models on prevalence data) are full of ties
        rng = np.random.default_rng(0)
        y = rng.integers(0, 2, size=200).astype(float)
        s = rng.integers(-2, 3, size=200).astype(float)
        ref = compute_auc(y, s)
        for seed in range(5):
            p = np.random.default_rng(seed).permutation(200)
            assert compute_auc(y[p], s[p]) == pytest.approx(ref, abs=1e-12)

    def test_tied_pair_counts_half(self):
        # one positive and one negative with the same score: AUC is exactly 0.5,
        # whichever comes first (the old trapezoid walk returned 0 or 1)
        assert compute_auc(np.array([1.0, 0.0]), np.array([3.0, 3.0])) == 0.5
        assert compute_auc(np.array([0.0, 1.0]), np.array([3.0, 3.0])) == 0.5

    def test_matches_mann_whitney(self):
        from scipy.stats import mannwhitneyu
        rng = np.random.default_rng(1)
        y = rng.integers(0, 2, size=150).astype(float)
        s = rng.integers(0, 4, size=150).astype(float)
        u = mannwhitneyu(s[y == 1], s[y == 0]).statistic
        assert compute_auc(y, s) == pytest.approx(u / ((y == 1).sum() * (y == 0).sum()), abs=1e-12)

    def test_worker_uses_the_same_auc(self):
        from app.services import worker
        assert worker.compute_auc is compute_auc


# ---------------------------------------------------------------------------
# Scoring formulas (no engine needed)
# ---------------------------------------------------------------------------

class TestScoreMatrix:
    X = np.array([[4.0, 0.0, 2.0], [0.0, 3.0, 1.0]])

    def test_prevalence_is_presence_not_row_normalisation(self):
        s = score_matrix(self.X, [1, -1, 1], "ternary", "prevalence")
        assert s.tolist() == [2.0, 0.0]

    def test_prevalence_uses_epsilon(self):
        x = np.array([[1e-6, 1.0]])
        assert score_matrix(x, [1, 1], "binary", "prev", epsilon=1e-5).tolist() == [1.0]

    def test_ratio_is_a_ratio(self):
        s = score_matrix(self.X, [1, -1, 1], "ratio", "raw", epsilon=1e-5)
        assert s[0] == pytest.approx(6.0 / 1e-5)
        assert s[1] == pytest.approx(1.0 / (3.0 + 1e-5))

    def test_log_skips_zeros(self):
        s = score_matrix(self.X, [1, 1, -1], "ternary", "log", epsilon=1.0)
        assert s[0] == pytest.approx(np.log(4.0) - np.log(2.0))
        assert s[1] == pytest.approx(np.log(3.0) - 0.0)

    def test_pow2_weights(self):
        s = score_matrix(self.X, [4, -2, 1], "pow2", "raw")
        assert s.tolist() == [18.0, -5.0]

    def test_zscore_needs_training_statistics(self):
        with pytest.raises(UnsupportedModelError):
            score_matrix(self.X, [1, 1, 1], "binary", "zscore")

    def test_zscore_stats_match_engine_definition(self):
        x = np.array([[1.0, 5.0], [3.0, 5.0], [5.0, 5.0]])
        mean, std = zscore_stats(x)
        assert mean.tolist() == [3.0, 5.0]
        assert std[0] == pytest.approx(np.sqrt(8.0 / 3.0))  # population std
        assert std[1] == 1.0                                 # constant feature

    @pytest.mark.parametrize("language", ["rf", "svm", "mcmc_generic", "xgboost"])
    def test_unsupported_models_are_refused(self, language):
        results = {
            "feature_names": ["a", "b"],
            "best_individual": {"features": {"0": 1}, "language": language,
                                "data_type": "raw", "threshold": 0.5},
        }
        x = pd.DataFrame([[1.0, 2.0]], index=["s1"], columns=["a", "b"])
        with pytest.raises(UnsupportedModelError):
            predict_from_model(results, x, features_in_rows=False)

    def test_predict_aligns_labels_by_name(self):
        results = {
            "feature_names": ["a"],
            "best_individual": {"features": {"0": 1}, "language": "binary",
                                "data_type": "raw", "threshold": 0.5},
        }
        x = pd.DataFrame({"a": [0.0, 1.0, 0.0, 1.0]}, index=["s1", "s2", "s3", "s4"])
        y = pd.Series([1, 0, 1, 0], index=["s4", "s3", "s2", "s1"])  # different order
        out = predict_from_model(results, x, y_labels=y, features_in_rows=False)
        assert out["evaluation"]["auc"] == 1.0
        assert out["evaluation"]["accuracy"] == 1.0


# ---------------------------------------------------------------------------
# Against the engine
# ---------------------------------------------------------------------------

def _fit(language: str, data_type: str, epsilon: float | None = None):
    gpredomicspy = pytest.importorskip("gpredomicspy")
    if not _HAVE_DATA:
        pytest.skip("sample dataset not available")
    out = tempfile.mkdtemp(prefix="predomics-scoring-")
    cfg = {
        "general": {"algo": "ga", "language": language, "data_type": data_type, "fit": "auc",
                    "seed": 42, "thread_number": 2, "k_penalty": 0.0001, "cv": False, "gpu": False},
        "ga": {"population_size": 120, "max_epochs": 3, "min_epochs": 1, "k_min": 1, "k_max": 20},
    }
    if epsilon is not None:
        cfg["general"]["epsilon"] = epsilon
    path = engine.write_param_yaml(
        cfg, str(_SAMPLE / "Xtrain.tsv"), str(_SAMPLE / "Ytrain.tsv"),
        str(_SAMPLE / "Xtest.tsv"), str(_SAMPLE / "Ytest.tsv"), output_dir=out,
    )
    param = gpredomicspy.Param()
    param.load(path)
    return gpredomicspy.fit(param), path


def _matrices(exp):
    fn = [str(f) for f in exp.feature_names()]
    sn = [str(s) for s in exp.sample_names()]
    xtr = matrix_io.load_matrix(str(_SAMPLE / "Xtrain.tsv")).reindex(index=sn, columns=fn)
    xte, _ = matrix_io.load_xy(str(_SAMPLE / "Xtest.tsv"), str(_SAMPLE / "Ytest.tsv"))
    return (xtr.to_numpy(dtype=float, na_value=0.0),
            xte.reindex(columns=fn).to_numpy(dtype=float, na_value=0.0))


@pytest.mark.parametrize(
    "language,data_type",
    list(itertools.product(["bin", "ter", "ratio", "pow2"], ["raw", "prev", "log", "zscore"])),
)
def test_python_scores_equal_engine_scores(language, data_type):
    exp, _ = _fit(language, data_type)
    xtr, xte = _matrices(exp)
    mean, std = zscore_stats(xtr)
    pop = exp.best_population()
    assert len(pop) > 0
    for i in range(min(len(pop), 15)):
        ind = pop.get_individual(i)
        m = dict(ind.get_metrics())
        feats = ind.get_features()
        idx = sorted(feats)
        coefs = np.array([float(feats[j]) for j in idx])
        for x, engine_scores, engine_classes in (
            (xtr, exp.predict_scores_train(i), exp.predict_classes_train(i)),
            (xte, exp.predict_scores_test(i), exp.predict_classes_test(i)),
        ):
            mine = score_matrix(x[:, idx], coefs, m["language"], m["data_type"], 1e-5, mean[idx], std[idx])
            ref = np.asarray(engine_scores, dtype=float)
            assert mine.shape == ref.shape
            np.testing.assert_allclose(mine, ref, rtol=1e-9, atol=1e-12)
            # same decision rule as the engine (no threshold CI in this run)
            assert ((ref >= m["threshold"]).astype(int) == np.asarray(engine_classes)).all()
    # the engine's reported AUC is tie-correct and equals ours on its own scores
    best = dict(pop.get_individual(0).get_metrics())
    assert compute_auc(np.asarray(exp.train_labels()), np.asarray(exp.predict_scores_train(0))) == \
        pytest.approx(best["auc"], abs=1e-9)


def test_engine_honours_the_configured_epsilon():
    """`general.epsilon` must reach the engine (it used to be silently ignored)."""
    eps = 1e-2
    exp, _ = _fit("ratio", "raw", epsilon=eps)
    xtr, _ = _matrices(exp)
    ind = exp.best_population().get_individual(0)
    feats = ind.get_features()
    idx = sorted(feats)
    coefs = np.array([float(feats[j]) for j in idx])
    ref = np.asarray(exp.predict_scores_train(0))
    np.testing.assert_allclose(score_matrix(xtr[:, idx], coefs, "ratio", "raw", eps), ref, rtol=1e-9)
    if (coefs < 0).any() and (coefs > 0).any():
        assert not np.allclose(score_matrix(xtr[:, idx], coefs, "ratio", "raw", 1e-5), ref, rtol=1e-6)


def test_worker_generation_test_auc_equals_engine():
    """The per-generation test curve is scored like the engine scores the test set."""
    from app.services import worker

    exp, param_path = _fit("ter", "prev")
    zstats = worker._train_zscore_stats(exp, __import__("yaml").safe_load(open(param_path)))
    ctx = worker._prepare_test_context(exp, param_path, zstats)
    assert ctx is not None
    best = exp.best_population().get_individual(0)
    np.testing.assert_allclose(
        worker._score_individual(best, ctx), np.asarray(exp.predict_scores_test(0)), rtol=1e-9, atol=1e-12,
    )
    expected = compute_auc(np.asarray(exp.test_labels()), np.asarray(exp.predict_scores_test(0)))
    assert worker._evaluate_one_generation(best, ctx) == pytest.approx(expected, abs=1e-6)


def test_zscore_model_predicts_from_stored_statistics():
    """Results carry the training statistics needed to apply a zscore model."""
    from app.services import worker
    import yaml

    exp, param_path = _fit("bin", "zscore")
    zstats = worker._train_zscore_stats(exp, yaml.safe_load(open(param_path)))
    best = exp.best_population().get_individual(0)
    m = dict(best.get_metrics())
    fn = [str(f) for f in exp.feature_names()]
    feats = best.get_features()
    results = {
        "feature_names": fn,
        "epsilon": 1e-5,
        "best_individual": {"features": {str(k): int(v) for k, v in feats.items()},
                            "language": m["language"], "data_type": m["data_type"],
                            "threshold": m["threshold"]},
        "zscore_stats": {fn[i]: list(zstats[fn[i]]) for i in feats},
    }
    x_test = pd.read_csv(_SAMPLE / "Xtest.tsv", sep="\t", index_col=0)
    y_test = pd.read_csv(_SAMPLE / "Ytest.tsv", sep="\t", index_col=0).iloc[:, 0]
    out = predict_from_model(results, x_test, y_labels=y_test, features_in_rows=True)
    np.testing.assert_allclose(out["scores"], np.asarray(exp.predict_scores_test(0)), atol=1e-5)
    assert out["predicted_classes"] == [int(c) for c in exp.predict_classes_test(0)]

    results.pop("zscore_stats")
    with pytest.raises(UnsupportedModelError):
        predict_from_model(results, x_test, features_in_rows=True)
