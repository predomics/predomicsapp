"""Analysis execution endpoints — run gpredomics and retrieve results."""

from __future__ import annotations
import copy
import hashlib
import itertools
import json
import logging
import uuid
from typing import Optional
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Body
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db, sync_session_factory
from ..core.deps import get_current_user, get_project_with_access
from ..models.db_models import User, Job, DatasetFile
from ..models.schemas import (
    RunConfig,
    BatchSweepConfig,
    ExperimentSummary,
    ExperimentDetail,
    IndividualResponse,
    JobStatus,
)
from ..services import engine, storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analysis", tags=["analysis"])


async def _verify_job_access(project_id, job_id, user, db):
    """Verify user has viewer access to the project, then return the job."""
    await get_project_with_access(project_id, user, db, require_role="viewer")
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.project_id == project_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{project_id}/run", response_model=ExperimentSummary)
async def run_analysis(
    project_id: str,
    config: RunConfig,
    x_file_id: str,
    y_file_id: str,
    xtest_file_id: str = "",
    ytest_file_id: str = "",
    job_name: str = "",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    """Launch a gpredomics analysis run (editor access required)."""
    await get_project_with_access(project_id, user, db, require_role="editor")

    # Resolve file paths via DatasetFile table
    async def _resolve_file(file_id: str) -> Optional[str]:
        r = await db.execute(select(DatasetFile).where(DatasetFile.id == file_id))
        f = r.scalar_one_or_none()
        return f.disk_path if f else None

    x_path = await _resolve_file(x_file_id)
    y_path = await _resolve_file(y_file_id)
    if not x_path or not y_path:
        raise HTTPException(status_code=404, detail="Dataset file not found")

    xtest_path = ""
    ytest_path = ""
    if xtest_file_id:
        xtest_path = await _resolve_file(xtest_file_id) or ""
    if ytest_file_id:
        ytest_path = await _resolve_file(ytest_file_id) or ""

    # Compute config hash for duplicate detection (nulls stripped for stability)
    config_hash = _compute_config_hash(config.model_dump(), {
        "x": x_file_id, "y": y_file_id,
        "xtest": xtest_file_id, "ytest": ytest_file_id,
    })

    # Create job record in database — commit immediately so the background
    # task (which uses a separate sync DB connection) can see the job.
    job = Job(
        project_id=project_id, user_id=user.id, name=job_name or None,
        status="pending", config=config.model_dump(), config_hash=config_hash,
    )
    db.add(job)
    await db.commit()

    job_dir = Path(storage.settings.project_dir) / project_id / "jobs" / job.id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Write param.yaml
    config_dict = config.model_dump()
    param_path = engine.write_param_yaml(
        config=config_dict,
        x_path=str(x_path),
        y_path=str(y_path),
        xtest_path=xtest_path,
        ytest_path=ytest_path,
        output_dir=str(job_dir),
    )

    # Run in background thread
    background_tasks.add_task(_run_job, job.id, project_id, param_path)

    return ExperimentSummary(job_id=job.id, name=job.name, status=JobStatus.pending)


# ---------------------------------------------------------------------------
# Batch runs — parameter sweeps
# ---------------------------------------------------------------------------

def _apply_sweep(config_dict: dict, key: str, value) -> dict:
    """Apply a single sweep value to a config dict (e.g. 'ga.population_size' = 5000)."""
    out = copy.deepcopy(config_dict)
    parts = key.split(".")
    if len(parts) == 2:
        section, param = parts
        if section in out:
            out[section][param] = value
    return out


@router.post("/{project_id}/batch")
async def run_batch(
    project_id: str,
    config: RunConfig,
    sweep: BatchSweepConfig,
    x_file_id: str,
    y_file_id: str,
    xtest_file_id: str = "",
    ytest_file_id: str = "",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    """Launch a batch of jobs from parameter sweeps (editor access required).

    The sweep config defines which parameters to vary. A cartesian product
    of all sweep values is computed, and one job is created per combination.
    Max 50 jobs per batch.
    """
    await get_project_with_access(project_id, user, db, require_role="editor")

    if not sweep.sweeps:
        raise HTTPException(status_code=400, detail="No sweep parameters defined")

    # Build cartesian product of sweep values
    keys = list(sweep.sweeps.keys())
    values = [sweep.sweeps[k] for k in keys]
    combinations = list(itertools.product(*values))

    if len(combinations) > 50:
        raise HTTPException(
            status_code=400,
            detail=f"Too many combinations ({len(combinations)}). Maximum is 50.",
        )

    # Resolve file paths
    async def _resolve(fid):
        if not fid:
            return ""
        r = await db.execute(select(DatasetFile).where(DatasetFile.id == fid))
        f = r.scalar_one_or_none()
        return f.disk_path if f else ""

    x_path = await _resolve(x_file_id)
    y_path = await _resolve(y_file_id)
    if not x_path or not y_path:
        raise HTTPException(status_code=404, detail="Dataset file not found")
    xtest_path = await _resolve(xtest_file_id)
    ytest_path = await _resolve(ytest_file_id)

    batch_id = uuid.uuid4().hex[:12]
    base_config = config.model_dump()
    job_summaries = []

    for combo in combinations:
        # Apply sweep overrides
        cfg = base_config
        name_parts = []
        for key, val in zip(keys, combo):
            cfg = _apply_sweep(cfg, key, val)
            short_key = key.split(".")[-1]
            name_parts.append(f"{short_key}={val}")

        job_name = f"[Batch] {' '.join(name_parts)}"

        config_hash = _compute_config_hash(cfg, {
            "x": x_file_id, "y": y_file_id,
            "xtest": xtest_file_id, "ytest": ytest_file_id,
        })

        job = Job(
            project_id=project_id, user_id=user.id, name=job_name,
            status="pending", config=cfg, config_hash=config_hash,
            batch_id=batch_id,
        )
        db.add(job)
        await db.flush()

        job_dir = Path(storage.settings.project_dir) / project_id / "jobs" / job.id
        job_dir.mkdir(parents=True, exist_ok=True)

        param_path = engine.write_param_yaml(
            config=cfg,
            x_path=str(x_path), y_path=str(y_path),
            xtest_path=xtest_path, ytest_path=ytest_path,
            output_dir=str(job_dir),
        )

        background_tasks.add_task(_run_job, job.id, project_id, param_path)
        job_summaries.append({"job_id": job.id, "name": job_name})

    await db.commit()

    return {
        "batch_id": batch_id,
        "job_count": len(job_summaries),
        "jobs": job_summaries,
    }


@router.get("/{project_id}/batches")
async def list_batches(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all batch runs for a project with summary stats."""
    await get_project_with_access(project_id, user, db, require_role="viewer")

    result = await db.execute(
        select(Job)
        .where(Job.project_id == project_id, Job.batch_id.isnot(None))
        .order_by(Job.created_at.desc())
    )
    jobs = result.scalars().all()

    batches: dict[str, list[Job]] = {}
    for j in jobs:
        batches.setdefault(j.batch_id, []).append(j)

    summaries = []
    for bid, batch_jobs in batches.items():
        completed = [j for j in batch_jobs if j.status == "completed"]
        best_auc = None
        best_job_id = None
        for j in completed:
            r = storage.get_job_result(project_id, j.id)
            if r:
                auc = r.get("best_individual", {}).get("auc")
                if auc is not None and (best_auc is None or auc > best_auc):
                    best_auc = auc
                    best_job_id = j.id

        summaries.append({
            "batch_id": bid,
            "job_count": len(batch_jobs),
            "completed": len(completed),
            "failed": sum(1 for j in batch_jobs if j.status == "failed"),
            "running": sum(1 for j in batch_jobs if j.status in ("pending", "running")),
            "best_auc": best_auc,
            "best_job_id": best_job_id,
            "created_at": batch_jobs[-1].created_at.isoformat() if batch_jobs else None,
        })

    return summaries


def _run_job(job_id: str, project_id: str, param_path: str) -> None:
    """Execute gpredomics in a subprocess so we can capture Rust log output.

    Runs in a Starlette thread pool — uses synchronous DB sessions to avoid
    event-loop conflicts with the async engine.
    """
    import os
    import subprocess
    import sys

    job_dir = Path(storage.settings.project_dir) / project_id / "jobs" / job_id
    log_path = job_dir / "console.log"
    results_path = job_dir / "results.json"

    # Mark job as running
    with sync_session_factory() as db:
        job = db.execute(select(Job).where(Job.id == job_id)).scalar_one()
        job.status = "running"
        db.commit()

    try:
        if not engine.HAS_ENGINE:
            # Mock mode — no subprocess needed
            mock_results = engine._mock_results()
            storage.save_job_result(project_id, job_id, mock_results)
            with open(log_path, "w") as lf:
                lf.write("[mock] Engine not available, using mock results\n")

            with sync_session_factory() as db:
                job = db.execute(select(Job).where(Job.id == job_id)).scalar_one()
                job.status = "completed"
                job.results_path = str(results_path)
                job.completed_at = datetime.now(timezone.utc)
                job.disk_size_bytes = _job_disk_size(project_id, job_id)
                db.commit()
            return

        # Run worker subprocess — stream output line-by-line for live console
        worker_module = "app.services.worker"
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        proc = subprocess.Popen(
            [sys.executable, "-u", "-m", worker_module, param_path, str(results_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(Path(__file__).resolve().parents[2]),  # backend/
            env=env,
        )

        # Read output line-by-line and flush to log file immediately
        with open(log_path, "w") as lf:
            for line in proc.stdout:
                lf.write(line.decode("utf-8", errors="replace"))
                lf.flush()

        proc.wait()

        if proc.returncode != 0:
            error_msg = log_path.read_text()[-500:] if log_path.exists() else "Unknown error"
            raise RuntimeError(f"Worker exited with code {proc.returncode}: {error_msg}")

        with sync_session_factory() as db:
            job = db.execute(select(Job).where(Job.id == job_id)).scalar_one()
            job.status = "completed"
            job.results_path = str(results_path)
            job.completed_at = datetime.now(timezone.utc)
            job.disk_size_bytes = _job_disk_size(project_id, job_id)
            db.commit()

        logger.info("Job %s completed", job_id)

    except Exception as e:
        # Append error to log
        with open(log_path, "a") as lf:
            lf.write(f"\n[error] {e}\n")

        with sync_session_factory() as db:
            job = db.execute(select(Job).where(Job.id == job_id)).scalar_one()
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.now(timezone.utc)
            db.commit()

        logger.error("Job %s failed: %s", job_id, e)


@router.get("/{project_id}/jobs/duplicates")
async def find_duplicate_jobs(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Find groups of jobs with identical config_hash (viewer access).

    Returns a list of duplicate groups, each with the hash and the job summaries.
    Only groups with 2+ jobs are returned. Within each group the best job
    (highest AUC, or most recent if no AUC) is marked as ``keep``.
    Backfills missing config_hash values on-the-fly.
    """
    await get_project_with_access(project_id, user, db, require_role="viewer")

    result = await db.execute(
        select(Job)
        .options(selectinload(Job.owner))
        .where(Job.project_id == project_id)
        .order_by(Job.created_at.desc())
    )
    all_jobs = result.scalars().all()

    # Backfill missing config_hash for older jobs
    dirty = False
    for j in all_jobs:
        if j.config_hash is None and j.config:
            j.config_hash = _compute_config_hash(j.config)
            dirty = True
    if dirty:
        await db.commit()

    # Group by config_hash
    groups: dict[str, list[Job]] = {}
    for j in all_jobs:
        if j.config_hash:
            groups.setdefault(j.config_hash, []).append(j)

    duplicates = []
    for h, group_jobs in groups.items():
        if len(group_jobs) < 2:
            continue
        # Pick the best: completed > failed > pending, then highest AUC, then newest
        def sort_key(j):
            status_rank = {"completed": 0, "running": 1, "failed": 2, "pending": 3}.get(j.status, 4)
            auc = 0.0
            if j.status == "completed":
                r = storage.get_job_result(project_id, j.id)
                if r:
                    auc = r.get("best_individual", {}).get("auc", 0.0) or 0.0
            return (status_rank, -auc, -(j.created_at.timestamp() if j.created_at else 0))
        group_jobs.sort(key=sort_key)
        best_id = group_jobs[0].id
        duplicates.append({
            "config_hash": h,
            "config_summary": _config_summary(group_jobs[0].config),
            "jobs": [
                {**_job_to_summary(j).model_dump(), "keep": j.id == best_id}
                for j in group_jobs
            ],
        })
    return duplicates


@router.get("/{project_id}/jobs/{job_id}/logs")
async def get_job_logs(
    project_id: str,
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the console log output for a job (viewer access)."""
    job = await _verify_job_access(project_id, job_id, user, db)

    log_path = Path(storage.settings.project_dir) / project_id / "jobs" / job_id / "console.log"
    log_content = ""
    if log_path.exists():
        log_content = log_path.read_text()

    return {
        "job_id": job_id,
        "status": job.status,
        "log": log_content,
    }


@router.get("/{project_id}/jobs/{job_id}", response_model=ExperimentSummary)
async def get_job_status(
    project_id: str,
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the status of a running or completed job (viewer access)."""
    await get_project_with_access(project_id, user, db, require_role="viewer")
    result = await db.execute(
        select(Job).options(selectinload(Job.owner)).where(Job.id == job_id, Job.project_id == project_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == "completed" and job.results_path:
        results = storage.get_job_result(project_id, job_id)
        if results:
            return _results_to_summary(job, results)

    return _job_to_summary(job)


@router.get("/{project_id}/jobs/{job_id}/detail", response_model=ExperimentDetail)
async def get_job_detail(
    project_id: str,
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed results of a completed job (viewer access)."""
    job = await _verify_job_access(project_id, job_id, user, db)

    results = storage.get_job_result(project_id, job_id)
    if not results:
        raise HTTPException(status_code=404, detail="Results not found")

    best = results.get("best_individual", {})
    return ExperimentDetail(
        job_id=job_id,
        name=job.name,
        status=JobStatus.completed,
        fold_count=results.get("fold_count", 0),
        generation_count=results.get("generation_count", 0),
        execution_time=results.get("execution_time", 0),
        feature_count=len(results.get("feature_names", [])),
        sample_count=len(results.get("sample_names", [])),
        best_auc=best.get("auc"),
        best_k=best.get("k"),
        feature_names=results.get("feature_names", []),
        sample_names=results.get("sample_names", []),
        best_individual=IndividualResponse(**best) if best else None,
    )


@router.get("/{project_id}/jobs/{job_id}/results")
async def get_job_results_raw(
    project_id: str,
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full results JSON including population and generation tracking (viewer access)."""
    await _verify_job_access(project_id, job_id, user, db)

    results = storage.get_job_result(project_id, job_id)
    if not results:
        raise HTTPException(status_code=404, detail="Results not found")

    return results


@router.get("/{project_id}/jobs")
async def list_jobs(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all jobs for a project (viewer access)."""
    await get_project_with_access(project_id, user, db, require_role="viewer")

    result = await db.execute(
        select(Job)
        .options(selectinload(Job.owner))
        .where(Job.project_id == project_id)
        .order_by(Job.created_at.desc())
    )
    jobs = result.scalars().all()

    # Backfill missing config_hash and disk_size_bytes for older jobs
    dirty = False
    for j in jobs:
        if j.config_hash is None and j.config:
            j.config_hash = _compute_config_hash(j.config)
            dirty = True
        if j.disk_size_bytes is None and j.status == "completed":
            j.disk_size_bytes = _job_disk_size(j.project_id, j.id)
            dirty = True
    if dirty:
        await db.commit()

    summaries = []
    for j in jobs:
        if j.status == "completed":
            results = storage.get_job_result(project_id, j.id)
            if results:
                summaries.append(_results_to_summary(j, results))
                continue
        summaries.append(_job_to_summary(j))
    return summaries


@router.delete("/{project_id}/jobs/{job_id}")
async def delete_job(
    project_id: str,
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a job and its results (editor access required)."""
    await get_project_with_access(project_id, user, db, require_role="editor")
    job = await _verify_job_access(project_id, job_id, user, db)

    if job.status == "running":
        raise HTTPException(status_code=409, detail="Cannot delete a running job")

    # Remove results files from disk
    job_dir = Path(storage.settings.project_dir) / project_id / "jobs" / job_id
    if job_dir.exists():
        import shutil
        shutil.rmtree(job_dir, ignore_errors=True)

    await db.execute(sa_delete(Job).where(Job.id == job_id))
    await db.commit()
    return {"detail": "Job deleted"}


def _strip_nulls(d):
    """Recursively remove keys with None values from a dict for stable hashing."""
    if not isinstance(d, dict):
        return d
    return {k: _strip_nulls(v) for k, v in d.items() if v is not None}


def _compute_config_hash(config: dict, file_ids: dict | None = None) -> str:
    """Compute a stable hash for a job configuration.

    Strips null values so that {epsilon: null} and omitted epsilon
    produce the same hash.  Optionally includes dataset file IDs.
    """
    normalized = _strip_nulls(config) if config else {}
    payload = {"config": normalized}
    if file_ids:
        payload.update(file_ids)
    return hashlib.md5(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()[:16]


def _config_summary(config: dict | None) -> str:
    """Build a short human-readable config summary string."""
    if not config:
        return ""
    gen = config.get("general", {})
    voting = config.get("voting", {})
    parts = []
    algo = gen.get("algo", "ga")
    parts.append(algo.upper())
    lang = gen.get("language", "")
    if lang:
        parts.append(f"lang={lang}")
    dt = gen.get("data_type", "")
    if dt:
        parts.append(f"dt={dt}")
    ga = config.get("ga", {})
    pop = ga.get("population_size")
    if pop:
        parts.append(f"pop={pop}")
    epochs = ga.get("max_epochs")
    if epochs:
        parts.append(f"ep={epochs}")
    if voting.get("vote"):
        parts.append(f"vote={voting.get('method', 'Majority')}")
    seed = gen.get("seed")
    if seed is not None:
        parts.append(f"seed={seed}")
    return " | ".join(parts)


def _job_disk_size(project_id: str, job_id: str) -> int | None:
    """Compute total size of a job directory on disk (bytes)."""
    job_dir = Path(storage.settings.project_dir) / project_id / "jobs" / job_id
    if not job_dir.is_dir():
        return None
    total = 0
    for f in job_dir.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total


def _job_to_summary(job: Job) -> ExperimentSummary:
    """Convert a Job ORM object to an ExperimentSummary (no results loaded)."""
    config = job.config or {}
    gen = config.get("general", {})
    ga = config.get("ga", {})
    duration = None
    if job.completed_at and job.created_at:
        duration = (job.completed_at - job.created_at).total_seconds()
    return ExperimentSummary(
        job_id=job.id,
        name=job.name,
        status=JobStatus(job.status),
        created_at=job.created_at.isoformat() if job.created_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        duration_seconds=duration,
        config_summary=_config_summary(config),
        user_name=job.owner.full_name if job.owner and job.owner.full_name else (job.owner.email if job.owner else None),
        language=gen.get("language"),
        data_type=gen.get("data_type"),
        population_size=ga.get("population_size"),
        config_hash=getattr(job, 'config_hash', None),
        disk_size_bytes=getattr(job, 'disk_size_bytes', None),
        batch_id=getattr(job, 'batch_id', None),
    )


def _results_to_summary(job: Job, results: dict) -> ExperimentSummary:
    """Convert a completed Job + results dict into a rich ExperimentSummary."""
    best = results.get("best_individual", {})
    config = job.config or {}
    gen = config.get("general", {})
    ga = config.get("ga", {})
    duration = None
    if job.completed_at and job.created_at:
        duration = (job.completed_at - job.created_at).total_seconds()
    return ExperimentSummary(
        job_id=job.id,
        name=job.name,
        status=JobStatus.completed,
        fold_count=results.get("fold_count", 0),
        generation_count=results.get("generation_count", 0),
        execution_time=results.get("execution_time", 0),
        feature_count=len(results.get("feature_names", [])),
        sample_count=len(results.get("sample_names", [])),
        best_auc=best.get("auc"),
        best_k=best.get("k"),
        created_at=job.created_at.isoformat() if job.created_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        duration_seconds=duration,
        config_summary=_config_summary(config),
        user_name=job.owner.full_name if job.owner and job.owner.full_name else (job.owner.email if job.owner else None),
        language=gen.get("language"),
        data_type=gen.get("data_type"),
        population_size=ga.get("population_size"),
        config_hash=getattr(job, 'config_hash', None),
        disk_size_bytes=getattr(job, 'disk_size_bytes', None),
        batch_id=getattr(job, 'batch_id', None),
    )
