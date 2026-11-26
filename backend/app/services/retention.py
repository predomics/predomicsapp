"""Retention: remove expired job results and old in-app backups.

Both rules are off by default (0 = keep forever) and nothing is ever deleted
while they are off:

* ``PREDOMICS_JOB_RETENTION_DAYS`` — finished (completed or failed) jobs whose
  end date is older than this many days lose their directory and their row.
* ``PREDOMICS_BACKUP_RETENTION_COUNT`` — only the newest N in-app backup
  archives are kept.

:func:`run_retention` is blocking (filesystem + sync DB session); call it via
``asyncio.to_thread``. :func:`start_scheduler` runs it once a day.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select

from ..core.config import settings
from ..core.database import sync_session_factory
from ..models.db_models import Job
from .quota import dir_size

_log = logging.getLogger(__name__)

_TERMINAL = ("completed", "failed")
_INTERVAL = 24 * 3600
_FIRST_RUN_DELAY = 300

_task: asyncio.Task | None = None


def _expired_jobs(days: int) -> list[Job]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with sync_session_factory() as db:
        ended = func.coalesce(Job.completed_at, Job.created_at)
        return list(db.execute(
            select(Job).where(Job.status.in_(_TERMINAL), ended < cutoff).order_by(ended)
        ).scalars().all())


def _backup_archives() -> list[Path]:
    backup_dir = Path(settings.data_dir) / "backups"
    if not backup_dir.is_dir():
        return []
    files = [f for f in backup_dir.glob("predomics_backup_*.tar.gz") if f.is_file()]
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)


def _sidecars(archive: Path) -> list[Path]:
    """Files written next to an archive (manifest) that go with it."""
    stem = archive.name[: -len(".tar.gz")]
    return [p for p in archive.parent.glob(stem + ".*") if p != archive and p.is_file()]


def run_retention(dry_run: bool = False) -> dict:
    """Apply the retention rules; with ``dry_run`` only report what would go.

    Returns ``{"dry_run", "job_retention_days", "backup_retention_count",
    "jobs": [{"job_id", "project_id", "name", "ended_at", "bytes"}],
    "backups": [{"file", "bytes"}], "bytes_freed"}``.
    """
    days = max(0, settings.job_retention_days)
    keep = max(0, settings.backup_retention_count)
    report = {
        "dry_run": dry_run,
        "job_retention_days": days,
        "backup_retention_count": keep,
        "jobs": [],
        "backups": [],
        "bytes_freed": 0,
    }

    if days:
        for job in _expired_jobs(days):
            job_dir = Path(settings.project_dir) / job.project_id / "jobs" / job.id
            size = dir_size(job_dir)
            ended = job.completed_at or job.created_at
            report["jobs"].append({
                "job_id": job.id,
                "project_id": job.project_id,
                "name": job.name,
                "ended_at": ended.isoformat() if ended else None,
                "bytes": size,
            })
            report["bytes_freed"] += size
            if dry_run:
                continue
            # Row first: a job without files is a visible, harmless leftover;
            # files without a row would be invisible garbage.
            with sync_session_factory() as db:
                row = db.get(Job, job.id)
                if row is not None and row.status in _TERMINAL:
                    db.delete(row)
                    db.commit()
            shutil.rmtree(job_dir, ignore_errors=True)

    if keep:
        for archive in _backup_archives()[keep:]:
            extra = _sidecars(archive)
            size = archive.stat().st_size + sum(p.stat().st_size for p in extra)
            report["backups"].append({"file": archive.name, "bytes": size})
            report["bytes_freed"] += size
            if dry_run:
                continue
            for p in [archive, *extra]:
                try:
                    p.unlink()
                except OSError as e:
                    _log.warning("Retention: could not delete %s: %s", p, e)

    if not dry_run and (report["jobs"] or report["backups"]):
        _log.info(
            "Retention removed %d job(s) and %d backup(s), freeing %.1f MB",
            len(report["jobs"]), len(report["backups"]), report["bytes_freed"] / 1048576,
        )
    return report


def is_enabled() -> bool:
    return settings.job_retention_days > 0 or settings.backup_retention_count > 0


async def _loop() -> None:
    await asyncio.sleep(_FIRST_RUN_DELAY)
    while True:
        try:
            await asyncio.to_thread(run_retention)
        except Exception:
            _log.exception("Retention run failed")
        await asyncio.sleep(_INTERVAL)


def start_scheduler() -> bool:
    """Start the daily retention task (call from the app lifespan). No-op when both rules are off."""
    global _task
    if not is_enabled() or (_task is not None and not _task.done()):
        return False
    _task = asyncio.get_running_loop().create_task(_loop(), name="predomics-retention")
    _log.info(
        "Retention scheduled daily (jobs: %s days, backups: keep %s)",
        settings.job_retention_days or "off", settings.backup_retention_count or "all",
    )
    return True


def stop_scheduler() -> None:
    """Cancel the retention task (call on shutdown)."""
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
