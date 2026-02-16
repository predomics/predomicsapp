"""MSP (Metagenomic Species Pan-genome) annotation service.

Fetches taxonomic annotations from biobanks.gmt.bio and caches locally.
Uses concurrent requests for fast bulk fetching.
"""

from __future__ import annotations
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)

BIOBANKS_API = "https://biobanks.gmt.bio/msp/"
CACHE_FILE = Path(settings.data_dir) / "cache" / "msp_annotations.json"

# In-memory cache (loaded from disk on first access)
_cache: dict[str, dict[str, Any]] | None = None


def _load_cache() -> dict[str, dict[str, Any]]:
    global _cache
    if _cache is not None:
        return _cache
    if CACHE_FILE.exists():
        try:
            _cache = json.loads(CACHE_FILE.read_text())
            logger.info("Loaded %d MSP annotations from cache", len(_cache))
        except Exception:
            _cache = {}
    else:
        _cache = {}
    return _cache


def _save_cache():
    if _cache is None:
        return
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(_cache, indent=1))


def _fetch_single(msp_id: str) -> tuple[str, dict[str, Any] | None]:
    """Fetch a single MSP annotation from the remote API."""
    try:
        resp = httpx.get(BIOBANKS_API, params={"msp": msp_id}, timeout=8.0)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                return msp_id, data[0]
    except Exception as e:
        logger.debug("Failed to fetch MSP %s: %s", msp_id, e)
    return msp_id, None


def get_annotations(feature_names: list[str]) -> dict[str, dict[str, Any]]:
    """Look up MSP annotations for a list of feature names.

    Only queries features that look like MSP identifiers (msp_NNNN pattern).
    Uses concurrent requests (max 20 threads) for fast bulk fetching.
    Returns a dict mapping feature name -> annotation dict.
    """
    cache = _load_cache()
    result = {}
    to_fetch = []

    for name in feature_names:
        if not name.lower().startswith("msp_"):
            continue
        if name in cache:
            result[name] = cache[name]
        else:
            to_fetch.append(name)

    if to_fetch:
        logger.info("Fetching %d MSP annotations from biobanks.gmt.bio", len(to_fetch))
        max_workers = min(20, len(to_fetch))
        fetched = 0
        failed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_fetch_single, msp_id): msp_id for msp_id in to_fetch}
            for future in as_completed(futures):
                msp_id, data = future.result()
                if data:
                    cache[msp_id] = data
                    result[msp_id] = data
                    fetched += 1
                else:
                    # Cache empty so we don't re-fetch
                    cache[msp_id] = {}
                    failed += 1
        logger.info("MSP fetch complete: %d succeeded, %d failed", fetched, failed)
        _save_cache()

    # Filter out empty entries (failed lookups)
    return {k: v for k, v in result.items() if v}
