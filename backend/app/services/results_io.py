"""Job result files — cached reads, atomic writes, small summaries.

``results.json`` files are large (tens of MB). Reading and parsing them is
blocking work, so request handlers must go through :func:`aload_results`
(which runs in a worker thread) and never call ``json.load`` directly.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from ..core.config import settings

# Parsed results kept in memory, bounded by the size of the files on disk.
_MAX_ENTRIES = 4
_MAX_TOTAL_BYTES = 200 * 1024 * 1024
_cache: "OrderedDict[tuple, tuple[int, dict]]" = OrderedDict()
_lock = threading.Lock()

SUMMARY_KEYS = ("fold_count", "generation_count", "execution_time")


def job_dir(project_id: str, job_id: str) -> Path:
    return Path(settings.project_dir) / project_id / "jobs" / job_id


def results_path(project_id: str, job_id: str) -> Path:
    return job_dir(project_id, job_id) / "results.json"


def write_json_atomic(path: str | os.PathLike, obj: Any, *, indent: int | None = None) -> None:
    """Write JSON to ``path`` so readers never see a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(obj, fh, indent=indent, default=str)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_results(project_id: str, job_id: str) -> dict | None:
    """Load a job's results (blocking). The returned dict is shared: do not mutate it."""
    path = results_path(project_id, job_id)
    try:
        st = path.stat()
    except OSError:
        return None
    key = (str(path), st.st_mtime_ns, st.st_size)
    with _lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            return hit[1]
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    with _lock:
        # Drop stale versions of the same file, then enforce the bounds.
        for k in [k for k in _cache if k[0] == key[0]]:
            del _cache[k]
        if st.st_size <= _MAX_TOTAL_BYTES:
            _cache[key] = (st.st_size, data)
            while len(_cache) > _MAX_ENTRIES or sum(v[0] for v in _cache.values()) > _MAX_TOTAL_BYTES:
                _cache.popitem(last=False)
    return data


async def aload_results(project_id: str, job_id: str) -> dict | None:
    """Load a job's results without blocking the event loop."""
    return await asyncio.to_thread(load_results, project_id, job_id)


def clear_cache() -> None:
    with _lock:
        _cache.clear()


# ---------------------------------------------------------------------------
# summary.json — the handful of numbers the status endpoint needs
# ---------------------------------------------------------------------------

def build_summary(results: dict) -> dict:
    best = results.get("best_individual") or {}
    return {
        "fold_count": results.get("fold_count", 0),
        "generation_count": results.get("generation_count", 0),
        "execution_time": results.get("execution_time", 0),
        "feature_count": len(results.get("feature_names", [])),
        "sample_count": len(results.get("sample_names", [])),
        "best_auc": best.get("auc"),
        "best_k": best.get("k"),
        "best_fit": best.get("fit"),
        "regression": bool(results.get("regression")),
        "mock": bool(results.get("mock")),
    }


def write_summary(project_id: str, job_id: str, results: dict) -> dict:
    summary = build_summary(results)
    write_json_atomic(job_dir(project_id, job_id) / "summary.json", summary)
    return summary


def load_summary(project_id: str, job_id: str) -> dict | None:
    """Return the job summary, building it from results.json once if missing (blocking)."""
    d = job_dir(project_id, job_id)
    spath, rpath = d / "summary.json", d / "results.json"
    try:
        if spath.exists() and (not rpath.exists() or spath.stat().st_mtime_ns >= rpath.stat().st_mtime_ns):
            return json.loads(spath.read_text())
    except (OSError, ValueError):
        pass
    results = load_results(project_id, job_id)
    if not results:
        return None
    try:
        return write_summary(project_id, job_id, results)
    except OSError:
        return build_summary(results)


def read_log_chunk(path: Path, offset: int = 0, max_bytes: int = 1024 * 1024) -> dict:
    """Read part of a console log.

    ``offset`` < 0 or 0 with a file larger than ``max_bytes`` returns the tail.
    Returns {"log", "size", "offset", "next_offset", "truncated"}.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return {"log": "", "size": 0, "offset": 0, "next_offset": 0, "truncated": False}
    truncated = False
    if offset <= 0:
        start = 0
        if size > max_bytes:
            start = size - max_bytes
            truncated = True
    else:
        start = min(offset, size)
    with open(path, "rb") as fh:
        fh.seek(start)
        raw = fh.read(max_bytes)
    return {
        "log": raw.decode("utf-8", errors="replace"),
        "size": size,
        "offset": start,
        "next_offset": start + len(raw),
        "truncated": truncated,
    }
