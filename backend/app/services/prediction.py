"""Prediction service — score samples with a trained gpredomics model.

gpredomicspy only scores the data an experiment was fitted on, so scoring
*new* samples (uploaded validation sets, the predict API, per-generation test
curves) has to be done here. The formulas below mirror
``gpredomics/src/individual.rs`` (``evaluate_raw``, ``evaluate_prevalence``,
``evaluate_log``, ``evaluate_zscore``) exactly; ``tests/test_audit_scoring.py``
checks them against the engine's own predictions. Anything the engine can do
that is not reproduced here raises :class:`UnsupportedModelError` rather than
returning a number that looks plausible and is wrong.
"""

from __future__ import annotations

import io
from typing import Mapping

import numpy as np
import pandas as pd

DEFAULT_EPSILON = 1e-5  # gpredomics `data_type_epsilon` default

_LANGUAGES = {
    "bin": "binary", "binary": "binary",
    "ter": "ternary", "ternary": "ternary",
    "pow2": "pow2",
    "ratio": "ratio",
    # OR (clause) languages: each term is a disjunctive clause scored by the max
    # of its features (gpredomics codes 4, 5 and 7; 6 = pow2-or is not implemented)
    "bin-or": "binary-or", "bin_or": "binary-or", "binary-or": "binary-or", "binary_or": "binary-or",
    "0-or": "binary-or",
    "ter-or": "ternary-or", "ter_or": "ternary-or", "ternary-or": "ternary-or", "ternary_or": "ternary-or",
    "1-or": "ternary-or",
    "ratio-or": "ratio-or", "ratio_or": "ratio-or", "3-or": "ratio-or",
}
_BASE_LANGUAGE = {"binary-or": "binary", "ternary-or": "ternary", "ratio-or": "ratio"}
OR_LANGUAGES = frozenset(_BASE_LANGUAGE)
_DATA_TYPES = {
    "raw": "raw",
    "prev": "prevalence", "prevalence": "prevalence",
    "log": "log",
    "zscore": "zscore", "z": "zscore", "standardized": "zscore",
}


class UnsupportedModelError(ValueError):
    """The model cannot be scored outside the engine (or needed data is missing)."""


def normalize_language(language) -> str:
    if language is None:
        return "binary"  # results without a language are plain linear models
    key = str(language).strip().lower()
    if key not in _LANGUAGES:
        raise UnsupportedModelError(
            f"Models of type '{language}' cannot be scored on new data "
            "(supported model languages: binary, ternary, pow2, ratio and their "
            "OR variants binary-or, ternary-or, ratio-or)."
        )
    return _LANGUAGES[key]


def is_or_language(language) -> bool:
    """True for the clause languages (binary-or, ternary-or, ratio-or), accepting aliases."""
    try:
        return normalize_language(language) in OR_LANGUAGES
    except UnsupportedModelError:
        return False


def base_language(language: str) -> str:
    """The arithmetic language an OR language is built on (``ternary-or`` -> ``ternary``)."""
    lang = normalize_language(language)
    return _BASE_LANGUAGE.get(lang, lang)


def clause_columns(clauses, feature_indices) -> list[list[int]]:
    """Translate clauses given as feature indices into positions of ``feature_indices``.

    ``feature_indices`` is the ordered list of model feature indices (one per
    column of the scored matrix). Features missing from it are dropped; an empty
    clause is dropped too.
    """
    pos = {int(idx): j for j, idx in enumerate(feature_indices)}
    out = []
    for clause in clauses or []:
        cols = [pos[int(f)] for f in clause if int(f) in pos]
        if cols:
            out.append(cols)
    return out


def normalize_data_type(data_type) -> str:
    key = str(data_type or "raw").strip().lower()
    if key not in _DATA_TYPES:
        raise UnsupportedModelError(f"Unknown model data type '{data_type}'.")
    return _DATA_TYPES[key]


def compute_auc(y_true, scores) -> float:
    """ROC AUC with correct handling of tied scores.

    Returns 0.5 when only one class is present (AUC is undefined there).
    """
    from sklearn.metrics import roc_auc_score

    y = np.asarray(y_true, dtype=float)
    s = np.asarray(scores, dtype=float)
    keep = ~(np.isnan(y) | np.isnan(s))
    y, s = y[keep], s[keep]
    pos = y == 1
    if pos.sum() == 0 or (~pos).sum() == 0:
        return 0.5
    return float(roc_auc_score(pos.astype(int), s))


# Backwards-compatible name (tests and older callers).
_compute_auc = compute_auc


def zscore_stats(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-feature mean and std as gpredomics computes them (``Data::compute_zscore_stats``).

    Population variance ``E[x^2] - mean^2`` over all samples; std is 1 when the
    variance is not positive.
    """
    x = np.nan_to_num(np.asarray(x, dtype=float), nan=0.0)
    n = x.shape[0]
    if n == 0:
        return np.zeros(x.shape[1]), np.ones(x.shape[1])
    mean = x.sum(axis=0) / n
    var = (x * x).sum(axis=0) / n - mean * mean
    std = np.where(var > 0, np.sqrt(np.where(var > 0, var, 1.0)), 1.0)
    return mean, std


def score_matrix(
    x: np.ndarray,
    coefs,
    language: str,
    data_type: str,
    epsilon: float = DEFAULT_EPSILON,
    means=None,
    stds=None,
    clauses=None,
) -> np.ndarray:
    """Score samples exactly as ``Individual::evaluate`` does.

    Parameters
    ----------
    x : array (n_samples, k)
        Untransformed values of the model's k features, one column per feature.
        Absent values must be 0 (the engine stores a sparse matrix without zeros).
    coefs : array (k,)
        Model coefficients (+-1 for binary/ternary/ratio, +-powers of two for pow2).
    means, stds : arrays (k,), required for ``zscore`` models
        Training-set statistics of each feature (see :func:`zscore_stats`).
    clauses : list of lists of column positions, for the OR languages
        Each clause is scored by the max of its transformed features and carries
        the coefficient of its features (one per clause). Without clauses, an OR
        model is scored as its base language (every feature is its own clause).
    """
    lang = normalize_language(language)
    or_model = lang in OR_LANGUAGES
    if or_model:
        lang = _BASE_LANGUAGE[lang]
    dtype = normalize_data_type(data_type)
    x = np.nan_to_num(np.asarray(x, dtype=float), nan=0.0)
    if x.ndim != 2:
        raise ValueError("x must be a 2-D array (samples x model features)")
    coefs = np.asarray(coefs, dtype=float)
    if x.shape[1] != coefs.shape[0]:
        raise ValueError("x has a different number of columns than the model has features")
    eps = float(epsilon)

    if dtype == "raw":
        t = x
    elif dtype == "prevalence":
        t = (x > eps).astype(float)
    elif dtype == "log":
        # Only stored (non-zero) values contribute: ln(v / epsilon).
        with np.errstate(divide="ignore", invalid="ignore"):
            t = np.where(x != 0, np.log(x / eps), 0.0)
    else:  # zscore
        if means is None or stds is None:
            raise UnsupportedModelError(
                "This model uses z-score standardised features, which needs the "
                "training-set mean and standard deviation of each feature. They are "
                "stored with results produced by current versions — re-run the job "
                "to enable prediction."
            )
        t = (x - np.asarray(means, dtype=float)) / np.asarray(stds, dtype=float)

    if or_model and clauses:
        # Mirrors Individual::evaluate_or_with: per clause the max of the transformed
        # values, weighted by |coef|, summed into positive and negative parts.
        positive = np.zeros(x.shape[0])
        negative = np.zeros(x.shape[0])
        for clause in clauses:
            cols = [int(c) for c in clause]
            if not cols:
                continue
            coef = coefs[cols[0]]
            if coef == 0:
                continue
            v = t[:, cols].max(axis=1) * abs(coef)
            if coef > 0:
                positive += v
            else:
                negative += v
        if lang == "ratio":
            with np.errstate(divide="ignore", invalid="ignore"):
                return positive / (negative + eps)
        return positive - negative

    if lang == "ratio":
        pos = coefs > 0
        if dtype == "log":
            t = t * np.abs(coefs)
        num = t[:, pos].sum(axis=1)
        den = t[:, ~pos].sum(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            return num / (den + eps)
    return t @ coefs


def model_feature_matrix(
    x_data: pd.DataFrame,
    feature_names: list[str],
    features: Mapping,
) -> tuple[np.ndarray, np.ndarray, list[str], list[str], list[str]]:
    """Extract the model's features from a samples x features frame.

    Returns (x, coefs, names, matched, missing). Features absent from the data
    are scored as 0, which is what the engine does for values it has not seen.
    """
    items = sorted(((int(i), float(c)) for i, c in features.items()), key=lambda p: p[0])
    names, coefs = [], []
    for idx, coef in items:
        if idx < 0 or idx >= len(feature_names):
            raise UnsupportedModelError(
                f"Model refers to feature index {idx}, outside the {len(feature_names)} known features."
            )
        names.append(str(feature_names[idx]))
        coefs.append(coef)
    cols = {str(c): i for i, c in enumerate(x_data.columns)}
    values = x_data.to_numpy(dtype=float, na_value=0.0) if len(x_data.columns) else np.zeros((len(x_data), 0))
    x = np.zeros((len(x_data), len(names)))
    matched, missing = [], []
    for j, name in enumerate(names):
        if name in cols:
            x[:, j] = values[:, cols[name]]
            matched.append(name)
        else:
            missing.append(name)
    return x, np.asarray(coefs, dtype=float), names, matched, missing


def predict_from_model(
    results: dict,
    x_data: pd.DataFrame,
    y_labels: pd.Series | None = None,
    features_in_rows: bool = True,
) -> dict:
    """Score samples with the best model of a completed job.

    Parameters
    ----------
    results : dict
        Full results JSON of a completed job (``best_individual``, ``feature_names``).
    x_data : pd.DataFrame
        Feature matrix. If *features_in_rows* is True, rows = features and
        columns = samples (the TSV convention used by gpredomics).
    y_labels : pd.Series or None
        Optional 0/1 class labels indexed by sample name. Samples are matched by
        name; evaluation metrics are computed on the matched samples.

    Returns
    -------
    dict with keys: sample_names, scores, predicted_classes, threshold,
    matched_features, missing_features, n_samples and, when labels are given,
    ``evaluation``.

    Raises
    ------
    UnsupportedModelError
        For models that cannot be scored here (scikit-learn baselines, MCMC
        models, z-score models without stored training statistics).
    """
    best = results.get("best_individual") or {}
    feature_names = results.get("feature_names", [])
    features = best.get("features") or {}
    if not features:
        raise UnsupportedModelError("The job has no model features to apply.")
    language = normalize_language(best.get("language"))
    clauses = best.get("clauses") if language in OR_LANGUAGES else None
    data_type = normalize_data_type(best.get("data_type", "raw"))
    threshold = float(best.get("threshold", 0.0))
    epsilon = float(results.get("epsilon") or DEFAULT_EPSILON)

    if features_in_rows:
        x_data = x_data.T
    x_data = x_data.apply(pd.to_numeric, errors="coerce")
    x_data.index = x_data.index.map(str)
    x_data.columns = x_data.columns.map(str)

    x, coefs, names, matched, missing = model_feature_matrix(x_data, feature_names, features)
    if not matched:
        raise UnsupportedModelError(
            "None of the model's features were found in the data — check the feature "
            "names and the matrix orientation."
        )

    means = stds = None
    if data_type == "zscore":
        stats = results.get("zscore_stats") or {}
        try:
            means = np.array([float(stats[n][0]) for n in names])
            stds = np.array([float(stats[n][1]) for n in names])
        except (KeyError, IndexError, TypeError, ValueError):
            means = stds = None  # score_matrix raises the explanatory error

    cols = clause_columns(clauses, sorted(int(i) for i in features)) if clauses else None
    scores = score_matrix(x, coefs, language, data_type, epsilon, means, stds, clauses=cols)
    predicted = (scores >= threshold).astype(int)
    sample_names = [str(s) for s in x_data.index]

    out = {
        "sample_names": sample_names,
        "scores": [round(float(s), 6) if np.isfinite(s) else None for s in scores],
        "predicted_classes": predicted.tolist(),
        "threshold": threshold,
        "matched_features": matched,
        "missing_features": missing,
        "n_samples": len(sample_names),
        "language": language,
        "data_type": data_type,
    }

    if y_labels is not None:
        y = pd.to_numeric(y_labels, errors="coerce")
        y.index = y.index.map(str)
        y = y[~y.index.duplicated(keep="first")].dropna()
        pos = {name: i for i, name in enumerate(sample_names)}
        common = [s for s in y.index if s in pos]
        if common:
            rows = np.array([pos[s] for s in common])
            y_arr = y.loc[common].to_numpy(dtype=float)
            s_arr = scores[rows]
            p_arr = predicted[rows]

            tp = int(np.sum((p_arr == 1) & (y_arr == 1)))
            tn = int(np.sum((p_arr == 0) & (y_arr == 0)))
            fp = int(np.sum((p_arr == 1) & (y_arr == 0)))
            fn = int(np.sum((p_arr == 0) & (y_arr == 1)))

            n = tp + tn + fp + fn
            accuracy = (tp + tn) / n if n > 0 else 0.0
            sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
            auc_defined = (tp + fn) > 0 and (tn + fp) > 0

            out["evaluation"] = {
                "auc": round(compute_auc(y_arr, s_arr), 6),
                "auc_defined": bool(auc_defined),
                "accuracy": round(accuracy, 6),
                "sensitivity": round(sensitivity, 6),
                "specificity": round(specificity, 6),
                "confusion_matrix": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
                "n_evaluated": n,
                "n_labels_unmatched": int(len(y) - len(common)),
            }

    return out


def parse_tsv(content: bytes) -> pd.DataFrame:
    """Parse a TSV file from bytes into a DataFrame."""
    return pd.read_csv(io.BytesIO(content), sep="\t", index_col=0)
