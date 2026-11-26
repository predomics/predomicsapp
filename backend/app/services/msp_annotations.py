"""MSP (Metagenomic Species Pan-genome) annotation service.

Fetches taxonomic annotations from biobanks.gmt.bio and caches them locally in
``<data_dir>/cache/msp_annotations.json``. All functions here are blocking:
call them through ``asyncio.to_thread`` from request handlers.

Cache entries:

* ``{"species": ..., ...}`` — an annotation (kept forever);
* ``{"_miss": <unix time>}`` — the service answered that it does not know this
  id; retried after :data:`MISS_TTL`.

Network errors, timeouts and server errors are **not** cached, so an outage of
the remote service cannot blank annotations permanently. Empty ``{}`` entries
written by older versions (which cached failures) are treated as expired.
"""

from __future__ import annotations
import json
import logging
import os
import re
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)

BIOBANKS_API = "https://biobanks.gmt.bio/msp/"
CACHE_FILE = Path(settings.data_dir) / "cache" / "msp_annotations.json"

MISS_TTL = 7 * 24 * 3600      # re-ask about unknown ids after a week
MAX_FEATURES = 5000           # per call
MAX_FETCH_WORKERS = 20
_MSP_ID_RE = re.compile(r"^msp_[0-9a-z]{1,12}$", re.IGNORECASE)

# In-memory cache (loaded from disk on first access)
_cache: dict[str, dict[str, Any]] | None = None
_lock = threading.RLock()       # protects _cache and the cache file
_fetch_lock = threading.Lock()  # one bulk fetch at a time (bounds outbound requests)

_MISS = object()   # definitive "unknown id"
_ERROR = object()  # transient failure, do not cache


def _load_cache() -> dict[str, dict[str, Any]]:
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
        loaded: dict = {}
        if CACHE_FILE.exists():
            try:
                data = json.loads(CACHE_FILE.read_text())
                if isinstance(data, dict):
                    loaded = data
                    logger.info("Loaded %d MSP annotations from cache", len(loaded))
            except Exception:
                logger.warning("MSP annotation cache is unreadable; starting empty")
        _cache = loaded
        return _cache


def _save_cache():
    """Persist the cache atomically (temp file + rename)."""
    with _lock:
        if _cache is None:
            return
        payload = json.dumps(_cache, indent=1)
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(CACHE_FILE.parent), prefix=".msp_annotations.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(payload)
            os.replace(tmp, CACHE_FILE)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def _msp_id(name: str) -> str:
    """Extract the bare MSP id from a feature name.

    Feature names may carry the taxonomy after the id
    (e.g. "msp_0074;Bacteria;Bacillota_A;..."); the API only accepts "msp_0074".
    """
    return name.split(";", 1)[0].strip()


def _is_fresh(entry: Any) -> bool:
    """True if a cache entry can be used without asking the service again."""
    if not isinstance(entry, dict) or not entry:
        return False  # legacy poisoned entry ({}), refetch
    miss = entry.get("_miss")
    if miss is None:
        return True
    try:
        return time.time() - float(miss) < MISS_TTL
    except (TypeError, ValueError):
        return False


def _fetch_single(msp_id: str):
    """Fetch one annotation. Returns (id, annotation dict | _MISS | _ERROR)."""
    try:
        resp = httpx.get(BIOBANKS_API, params={"msp": msp_id}, timeout=8.0)
    except Exception as e:  # network error / timeout
        logger.debug("Failed to fetch MSP %s: %s", msp_id, e)
        return msp_id, _ERROR
    if resp.status_code == 404:
        return msp_id, _MISS
    if resp.status_code != 200:
        return msp_id, _ERROR
    try:
        data = resp.json()
    except ValueError:
        return msp_id, _ERROR
    if isinstance(data, list):
        if data and isinstance(data[0], dict) and data[0]:
            return msp_id, data[0]
        return msp_id, _MISS
    return msp_id, _ERROR


def get_annotations(feature_names: list[str]) -> dict[str, dict[str, Any]]:
    """Look up MSP annotations for a list of feature names (blocking).

    Only names that look like MSP identifiers (``msp_NNNN``, optionally followed
    by ``;taxonomy``) are queried; anything else, including non-string items, is
    ignored. At most :data:`MAX_FEATURES` names are considered per call.
    Returns a dict mapping feature name (as given) -> annotation dict.
    """
    cache = _load_cache()
    result: dict[str, dict[str, Any]] = {}
    to_fetch: list[str] = []
    names_by_id: dict[str, list[str]] = {}

    with _lock:
        for name in feature_names[:MAX_FEATURES]:
            if not isinstance(name, str):
                continue
            msp_id = _msp_id(name)
            if not _MSP_ID_RE.match(msp_id):
                continue
            first_time = msp_id not in names_by_id
            names_by_id.setdefault(msp_id, []).append(name)
            entry = cache.get(msp_id)
            if _is_fresh(entry):
                if "_miss" not in entry:
                    result[name] = entry
            elif first_time:
                to_fetch.append(msp_id)

    if to_fetch:
        with _fetch_lock:
            # Another request may have fetched some of these while we waited.
            with _lock:
                still = []
                for msp_id in to_fetch:
                    entry = cache.get(msp_id)
                    if _is_fresh(entry):
                        if "_miss" not in entry:
                            for name in names_by_id[msp_id]:
                                result[name] = entry
                    else:
                        still.append(msp_id)
            if still:
                logger.info("Fetching %d MSP annotations from biobanks.gmt.bio", len(still))
                fetched = missed = failed = 0
                with ThreadPoolExecutor(max_workers=min(MAX_FETCH_WORKERS, len(still))) as executor:
                    futures = [executor.submit(_fetch_single, msp_id) for msp_id in still]
                    for future in as_completed(futures):
                        msp_id, data = future.result()
                        with _lock:
                            if data is _ERROR:
                                failed += 1
                            elif data is _MISS:
                                cache[msp_id] = {"_miss": time.time()}
                                missed += 1
                            else:
                                cache[msp_id] = data
                                for name in names_by_id[msp_id]:
                                    result[name] = data
                                fetched += 1
                logger.info(
                    "MSP fetch complete: %d found, %d unknown, %d failed (will retry)",
                    fetched, missed, failed,
                )
                if fetched or missed:
                    try:
                        _save_cache()
                    except OSError as e:
                        logger.warning("Could not save MSP annotation cache: %s", e)

    return result
