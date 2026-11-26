"""Shared loader for abundance matrices and label files.

One place that knows the on-disk conventions:

* X is a TSV whose first column holds names. With ``features_in_rows=True``
  (the gpredomics convention) rows are features and columns are samples;
  otherwise rows are samples.
* y is a TSV whose first column holds sample names and second column the label.

Everything returned is oriented **samples x features** and aligned by sample
name, never by position. Parsed files are cached by (path, mtime, size) so the
many Data Explore endpoints do not re-read the same file.
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict

import numpy as np
import pandas as pd

_MAX_ENTRIES = 8
_MAX_TOTAL_BYTES = 1024 * 1024 * 1024  # in-memory size of cached frames
_cache: "OrderedDict[tuple, tuple[int, object]]" = OrderedDict()
_lock = threading.Lock()


def _file_key(path: str) -> tuple:
    st = os.stat(path)
    return (os.path.abspath(path), st.st_mtime_ns, st.st_size)


def _cached(key: tuple, loader):
    with _lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            return hit[1]
    value = loader()
    try:
        nbytes = int(value.memory_usage(deep=True).sum()) if isinstance(value, pd.DataFrame) \
            else int(value.memory_usage(deep=True))
    except Exception:
        nbytes = 0
    with _lock:
        for k in [k for k in _cache if k[0] == key[0] and k != key and k[3:] == key[3:]]:
            del _cache[k]
        if nbytes <= _MAX_TOTAL_BYTES:
            _cache[key] = (nbytes, value)
            while len(_cache) > _MAX_ENTRIES or sum(v[0] for v in _cache.values()) > _MAX_TOTAL_BYTES:
                _cache.popitem(last=False)
    return value


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def load_matrix(path: str, features_in_rows: bool = True) -> pd.DataFrame:
    """Return the matrix as a float DataFrame, rows = samples, columns = features.

    Non-numeric cells become NaN. The frame is shared with the cache: treat it
    as read-only (derive new frames instead of assigning into it).
    """
    key = _file_key(path) + ("X", bool(features_in_rows))

    def _load() -> pd.DataFrame:
        df = pd.read_csv(path, sep="\t", index_col=0)
        if features_in_rows:
            df = df.T
        df = df.apply(pd.to_numeric, errors="coerce").astype(float)
        df.index = df.index.map(str)
        df.columns = df.columns.map(str)
        return df

    return _cached(key, _load)


def load_labels(path: str) -> pd.Series:
    """Return the labels as a Series indexed by sample name (first data column)."""
    key = _file_key(path) + ("y", False)

    def _load() -> pd.Series:
        df = pd.read_csv(path, sep="\t", index_col=0)
        if df.shape[1] == 0:
            raise ValueError(f"Label file has no label column: {os.path.basename(path)}")
        s = df.iloc[:, 0]
        s.index = s.index.map(str)
        return s[~s.index.duplicated(keep="first")]

    return _cached(key, _load)


def load_xy(
    x_path: str, y_path: str, features_in_rows: bool = True,
) -> tuple[pd.DataFrame, pd.Series]:
    """Load X and y restricted to their common samples, in X order, aligned by name."""
    X = load_matrix(x_path, features_in_rows)
    y = load_labels(y_path)
    common = X.index.intersection(y.index)
    if len(common) == 0:
        raise ValueError(
            "X and y have no sample names in common — check the matrix orientation "
            "(features in rows vs samples in rows) and the sample identifiers."
        )
    return X.loc[common], y.loc[common]


def class_codes(y: pd.Series) -> np.ndarray:
    """Integer class codes for a classification label vector.

    Raises a clear error for missing or non-integer labels instead of silently
    truncating continuous targets into classes.
    """
    vals = pd.to_numeric(y, errors="coerce")
    if vals.isna().any():
        raise ValueError("Labels contain missing or non-numeric values")
    arr = vals.to_numpy(dtype=float)
    if not np.all(np.equal(np.mod(arr, 1), 0)):
        raise ValueError(
            "Labels are not integer class codes (this view needs a classification target)"
        )
    return arr.astype(int)


def detect_features_in_rows(x_path: str, y_path: str, default: bool = True) -> bool:
    """Guess the orientation of X from where y's sample names appear.

    If the sample names of the label file are found in X's header row, features
    are in rows (the gpredomics convention); if they are found in X's first
    column, samples are in rows. Falls back to ``default`` when undecidable.
    """
    key = _file_key(x_path) + ("orient", _file_key(y_path))

    def _detect() -> pd.Series:
        try:
            samples = set(load_labels(y_path).index)
            header = pd.read_csv(x_path, sep="\t", index_col=0, nrows=0)
            first_col = pd.read_csv(x_path, sep="\t", usecols=[0])
            in_cols = len(samples.intersection(map(str, header.columns)))
            in_rows = len(samples.intersection(map(str, first_col.iloc[:, 0])))
            if in_cols == in_rows:
                value = default
            else:
                value = in_cols > in_rows
        except Exception:  # unreadable file: let the real loader report it
            value = default
        return pd.Series([bool(value)])

    return bool(_cached(key, _detect).iloc[0])
