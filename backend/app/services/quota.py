"""Per-user storage accounting and quota.

A user's usage is everything the app stores on their behalf: the files of their
dataset library (including files kept for older dataset versions) and the job
directories (results, logs, parameters) of the projects they own.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.errors import ApiError
from ..models.db_models import Project

_MB = 1024 * 1024


def quota_bytes() -> int:
    """The per-user quota in bytes; 0 means unlimited."""
    return max(0, settings.user_quota_mb) * _MB


def dir_size(path: Path) -> int:
    """Total size of the regular files under ``path`` (0 if it does not exist). Blocking."""
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    st = os.lstat(os.path.join(root, name))
                except OSError:
                    continue
                total += st.st_size
    except OSError:
        pass
    return total


def _usage(user_id: str, project_ids: list[str]) -> int:
    total = dir_size(Path(settings.data_dir) / "datasets" / user_id)
    for pid in project_ids:
        total += dir_size(Path(settings.project_dir) / pid)
    return total


async def user_usage_bytes(db: AsyncSession, user_id: str) -> int:
    """Bytes currently stored for ``user_id``."""
    rows = await db.execute(select(Project.id).where(Project.user_id == user_id))
    project_ids = [r[0] for r in rows.all()]
    return await asyncio.to_thread(_usage, user_id, project_ids)


async def check_quota(db: AsyncSession, user_id: str, incoming_bytes: int) -> None:
    """Raise a 413 (code ``QUOTA_EXCEEDED``) if storing ``incoming_bytes`` more would pass the quota."""
    limit = quota_bytes()
    if not limit:
        return
    used = await user_usage_bytes(db, user_id)
    if used + max(0, incoming_bytes) > limit:
        raise ApiError(
            413,
            f"Storage quota exceeded: you use {used / _MB:.0f} MB of {limit / _MB:.0f} MB "
            f"and this file needs {max(0, incoming_bytes) / _MB:.1f} MB more. "
            "Delete datasets or jobs you no longer need, or ask an administrator for more space.",
            code="QUOTA_EXCEEDED",
        )
