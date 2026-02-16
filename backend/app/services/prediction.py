"""Prediction service — apply trained model coefficients to new data."""

from __future__ import annotations

import io
import math

import numpy as np
import pandas as pd


def predict_from_model(
    results: dict,
    x_data: pd.DataFrame,
    y_labels: pd.Series | None = None,
    features_in_rows: bool = True,
) -> dict:
    """Score samples using coefficients from a completed job.

    Parameters
    ----------
    results : dict
        Full results JSON from a completed job (must contain
        ``best_individual.features`` and ``feature_names``).
    x_data : pd.DataFrame
        Feature matrix. If *features_in_rows* is True, rows = features and
        columns = samples (the TSV convention used by gpredomics).
    y_labels : pd.Series or None
        Optional class labels (0/1). When provided, evaluation metrics
        (AUC, accuracy, sensitivity, specificity, confusion matrix) are
        computed.
    features_in_rows : bool
        If True the matrix is transposed so that rows become samples.

    Returns
    -------
    dict with keys: sample_names, scores, predicted_classes, threshold,
    matched_features, missing_features, and optionally evaluation metrics.
    """
    best = results.get("best_individual", {})
    feature_names = results.get("feature_names", [])
    features = best.get("features", {})  # {index_str: coefficient}
    data_type = best.get("data_type", "raw")
    threshold = best.get("threshold", 0.0)

    # Transpose if features are in rows
    if features_in_rows:
        x_data = x_data.T

    # Apply prevalence normalisation if the model used it
    x_raw = x_data.values.astype(float)
    if data_type == "prevalence":
        row_sums = x_raw.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1.0
        x_eval = x_raw / row_sums
    else:
        x_eval = x_raw

    # Map feature index → column index in the new data
    col_idx = {name: i for i, name in enumerate(x_data.columns)}
    matched = []
    missing = []
    scores = np.zeros(len(x_eval))

    for idx_str, coef in features.items():
        idx = int(idx_str)
        if idx >= len(feature_names):
            continue
        feat_name = feature_names[idx]
        if feat_name in col_idx:
            scores += x_eval[:, col_idx[feat_name]] * float(coef)
            matched.append(feat_name)
        else:
            missing.append(feat_name)

    predicted = (scores >= threshold).astype(int).tolist()
    sample_names = x_data.index.tolist()

    out = {
        "sample_names": [str(s) for s in sample_names],
        "scores": [round(float(s), 6) for s in scores],
        "predicted_classes": predicted,
        "threshold": float(threshold),
        "matched_features": matched,
        "missing_features": missing,
        "n_samples": len(sample_names),
    }

    # Evaluation metrics if labels provided
    if y_labels is not None:
        common = x_data.index.intersection(y_labels.index)
        if len(common) > 0:
            y_arr = y_labels.loc[common].values.astype(float)
            s_arr = np.array([scores[x_data.index.get_loc(c)] for c in common])
            p_arr = np.array([predicted[x_data.index.get_loc(c)] for c in common])

            tp = int(np.sum((p_arr == 1) & (y_arr == 1)))
            tn = int(np.sum((p_arr == 0) & (y_arr == 0)))
            fp = int(np.sum((p_arr == 1) & (y_arr == 0)))
            fn = int(np.sum((p_arr == 0) & (y_arr == 1)))

            n = tp + tn + fp + fn
            accuracy = (tp + tn) / n if n > 0 else 0.0
            sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
            auc = _compute_auc(y_arr, s_arr)

            out["evaluation"] = {
                "auc": round(auc, 6),
                "accuracy": round(accuracy, 6),
                "sensitivity": round(sensitivity, 6),
                "specificity": round(specificity, 6),
                "confusion_matrix": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
                "n_evaluated": n,
            }

    return out


def parse_tsv(content: bytes) -> pd.DataFrame:
    """Parse a TSV file from bytes into a DataFrame."""
    return pd.read_csv(io.BytesIO(content), sep="\t", index_col=0)


def _compute_auc(y_true: np.ndarray, scores: np.ndarray) -> float:
    """Compute AUC using the trapezoidal rule (no sklearn dependency)."""
    order = np.argsort(-scores)
    y_sorted = y_true[order]
    n_pos = int(np.sum(y_sorted == 1))
    n_neg = len(y_sorted) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    tp = fp = 0
    auc = 0.0
    tpr_prev = fpr_prev = 0.0
    for label in y_sorted:
        if label == 1:
            tp += 1
        else:
            fp += 1
        tpr = tp / n_pos
        fpr = fp / n_neg
        auc += (fpr - fpr_prev) * (tpr + tpr_prev) / 2
        tpr_prev, fpr_prev = tpr, fpr
    return float(auc)
