"""scikit-learn baselines must match samples by name (audit finding BE-F7)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services import sklearn_runner


def _write(tmp_path, shuffle_y: bool, drop: int = 0, samples_in_rows: bool = False):
    rng = np.random.default_rng(3)
    n = 80
    samples = [f"s{i:03d}" for i in range(n)]
    y = np.array([i % 2 for i in range(n)])
    X = pd.DataFrame(
        {"signal": y * 5.0 + rng.normal(0, 0.1, n), "noise1": rng.normal(0, 1, n), "noise2": rng.normal(0, 1, n)},
        index=samples,
    )
    x_path = tmp_path / ("X_rows.tsv" if samples_in_rows else "X.tsv")
    (X if samples_in_rows else X.T).to_csv(x_path, sep="\t", index_label="id")
    ydf = pd.DataFrame({"class": y}, index=samples)
    if drop:
        ydf = ydf.iloc[drop:]
    if shuffle_y:
        ydf = ydf.sample(frac=1.0, random_state=11)
    y_path = tmp_path / f"y_{int(shuffle_y)}_{drop}.tsv"
    ydf.to_csv(y_path, sep="\t", index_label="id")
    return str(x_path), str(y_path)


def _run(x_path, y_path, features_in_rows=True, xtest="", ytest=""):
    param = {
        "general": {"algo": "logistic", "seed": 42, "cv": False},
        "data": {"X": x_path, "y": y_path, "Xtest": xtest, "ytest": ytest,
                 "features_in_rows": features_in_rows, "holdout_ratio": 0.25},
    }
    return sklearn_runner.run_sklearn(param, {"penalty": "l2", "C": 1.0})


def test_shuffled_labels_give_the_same_model(tmp_path):
    """Before the fix, a y file in another order silently mislabelled the samples."""
    x, y_sorted = _write(tmp_path, shuffle_y=False)
    _, y_shuffled = _write(tmp_path, shuffle_y=True)
    a = _run(x, y_sorted)
    b = _run(x, y_shuffled)
    assert a["train_metrics"]["auc"] == pytest.approx(1.0, abs=1e-6)
    assert b["train_metrics"]["auc"] == pytest.approx(1.0, abs=1e-6)   # was ~0.5 by position
    assert b["test_metrics"]["auc"] == pytest.approx(1.0, abs=1e-6)
    assert a["importance"][0]["feature"] == b["importance"][0]["feature"] == "signal"


def test_samples_missing_from_labels_are_dropped_not_shifted(tmp_path):
    x, y = _write(tmp_path, shuffle_y=True, drop=7)
    res = _run(x, y)
    assert res["train_metrics"]["auc"] == pytest.approx(1.0, abs=1e-6)
    dropped = {f"s{i:03d}" for i in range(7)}
    assert not dropped.intersection(res["sample_names"])
    assert 50 <= len(res["sample_names"]) <= 58          # ~75% of the 73 labelled samples


def test_test_set_is_matched_by_feature_and_sample_name(tmp_path):
    x, y = _write(tmp_path, shuffle_y=False)
    # test matrix with features in another order and labels shuffled
    X = pd.read_csv(x, sep="\t", index_col=0)
    xt = tmp_path / "Xtest.tsv"
    X.loc[["noise2", "signal", "noise1"]].to_csv(xt, sep="\t", index_label="id")
    _, yt = _write(tmp_path, shuffle_y=True)
    res = _run(x, y, xtest=str(xt), ytest=yt)
    assert res["test_metrics"]["auc"] == pytest.approx(1.0, abs=1e-6)


def test_samples_in_rows_orientation(tmp_path):
    x, y = _write(tmp_path, shuffle_y=True, samples_in_rows=True)
    res = _run(x, y, features_in_rows=False)
    assert res["feature_names"] == ["signal", "noise1", "noise2"]
    assert res["train_metrics"]["auc"] == pytest.approx(1.0, abs=1e-6)


def test_no_common_samples_is_an_error(tmp_path):
    x, _ = _write(tmp_path, shuffle_y=False)
    y = tmp_path / "other.tsv"
    pd.DataFrame({"class": [0, 1]}, index=["zz1", "zz2"]).to_csv(y, sep="\t", index_label="id")
    with pytest.raises(ValueError):
        _run(x, str(y))
