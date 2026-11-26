"""Analysis execution endpoints — run gpredomics and retrieve results."""

from __future__ import annotations
import asyncio
import copy
import hashlib
import itertools
import json
import logging
import shutil
import uuid
from datetime import datetime, timezone

import yaml
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, File, UploadFile, Form
from pydantic import ValidationError
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.deps import get_current_user, get_project_access
from ..core.uploads import read_upload
from ..models.db_models import User, Job, Dataset, DatasetFile, ProjectDataset
from ..models.schemas import (
    RunConfig,
    BatchSweepConfig,
    ExperimentSummary,
    ExperimentDetail,
    IndividualResponse,
    JobStatus,
)
from ..services import engine, storage, audit, scitq_client, jobs, results_io
from ..services.prediction import predict_from_model, parse_tsv, UnsupportedModelError
from typing import List
from ..models.schemas import (
    BatchLaunch, BatchSummary, Detail, DuplicateGroup, ExperimentSummary, JobConfigResponse, JobLogs, JobProgress, JobResults, StabilityAnalysis, ValidationResult,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analysis", tags=["analysis"])

MAX_BATCH_JOBS = 50

# Historical names, kept for callers and tests.
_run_job = jobs.run_local_job
_poll_scitq_job = jobs.poll_scitq_job
_fire_webhooks = jobs.fire_webhooks
_job_disk_size = jobs.job_disk_size


async def _verify_job_access(project_id, job_id, user, db):
    """Verify user has viewer access to the project, then return the job."""
    await get_project_access(project_id, user, db, require_role="viewer")
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.project_id == project_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


async def _project_file_path(db: AsyncSession, project_id: str, file_id: str, what: str) -> str:
    """Disk path of a dataset file, only if its dataset is assigned to this project.

    A file id alone is not an authorisation: without the project link check any
    editor of any project could run jobs on other users' data.
    """
    if not file_id:
        return ""
    r = await db.execute(
        select(DatasetFile)
        .join(Dataset, DatasetFile.dataset_id == Dataset.id)
        .join(ProjectDataset, ProjectDataset.dataset_id == Dataset.id)
        .where(DatasetFile.id == file_id, ProjectDataset.project_id == project_id)
    )
    f = r.scalars().first()
    if f is None or not f.disk_path:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset file not found in this project ({what})",
        )
    return f.disk_path


async def _original_job_files(db: AsyncSession, project_id: str, job_id: str) -> dict:
    """Dataset files a job ran on, read back from the param.yaml written at launch.

    Returns {"X", "y", "Xtest", "ytest", "clinical"} -> DatasetFile (or None when
    the job had no such input). Raises 409 when the original training files are
    no longer available in this project: re-running on other files would give
    results that silently belong to different data.
    """
    param_path = Path(storage.settings.project_dir) / project_id / "jobs" / job_id / "param.yaml"
    try:
        param = yaml.safe_load(param_path.read_text()) or {}
    except (OSError, yaml.YAMLError):
        param = {}
    data = param.get("data") or {}
    paths = {
        "X": data.get("X") or "", "y": data.get("y") or "",
        "Xtest": data.get("Xtest") or "", "ytest": data.get("ytest") or "",
        "clinical": (param.get("clinical") or {}).get("path") or "",
    }
    wanted = [p for p in paths.values() if p]
    by_path = {}
    if wanted:
        r = await db.execute(
            select(DatasetFile)
            .join(Dataset, DatasetFile.dataset_id == Dataset.id)
            .join(ProjectDataset, ProjectDataset.dataset_id == Dataset.id)
            .where(ProjectDataset.project_id == project_id, DatasetFile.disk_path.in_(wanted))
        )
        by_path = {f.disk_path: f for f in r.scalars().all()}
    files = {role: by_path.get(p) if p else None for role, p in paths.items()}
    missing = [role for role, p in paths.items() if p and files[role] is None]
    if not paths["X"] or not paths["y"] or missing:
        raise HTTPException(
            status_code=409,
            detail="The data files of the original job are no longer available in this project"
                   + (f" ({', '.join(missing)})" if missing else "")
                   + "; launch a new run instead.",
        )
    return files


def _prepare_config(config: RunConfig | dict, label: str = "") -> dict:
    """Plain config dict, thread count capped to the server limit, GA selection checked."""
    cfg = config.model_dump() if isinstance(config, RunConfig) else copy.deepcopy(config)
    general = cfg.setdefault("general", {})
    general["thread_number"] = jobs.effective_threads(general.get("thread_number", 4))
    # A GA run that cannot select two parents makes the engine panic at the first
    # generation: refuse it now, with the values to change.
    try:
        engine.check_ga_selection(cfg)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{label}: {exc}" if label else str(exc))
    return cfg


async def _launch(job: Job, project_id: str, param_path: str, job_dir: Path, user: User,
                  db: AsyncSession, background_tasks: BackgroundTasks | None) -> None:
    """Hand a committed job to scitq (if enabled) or to the local job runner."""
    if scitq_client.is_enabled():
        try:
            scitq_task_id = await asyncio.to_thread(
                scitq_client.dispatch_job, job.id, project_id, param_path, str(job_dir),
            )
            job.scitq_task_id = scitq_task_id
            await db.commit()
            jobs.submit_scitq_poller(job.id, project_id, scitq_task_id, user.id, background_tasks)
            return
        except Exception as e:  # noqa: BLE001
            logger.error("scitq dispatch failed, falling back to local: %s", e)
    jobs.submit_local(job.id, project_id, param_path, user.id, background_tasks)


@router.post("/{project_id}/run", response_model=ExperimentSummary)
async def run_analysis(
    project_id: str,
    config: RunConfig,
    x_file_id: str,
    y_file_id: str,
    xtest_file_id: str = "",
    ytest_file_id: str = "",
    clinical_file_id: str = "",
    job_name: str = "",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    """Launch a gpredomics analysis run (editor access required)."""
    await get_project_access(project_id, user, db, require_role="editor")

    # Resolve file paths — every file must belong to a dataset of this project
    x_path = await _project_file_path(db, project_id, x_file_id, "X train")
    y_path = await _project_file_path(db, project_id, y_file_id, "y train")
    if not x_path or not y_path:
        raise HTTPException(status_code=404, detail="Dataset file not found")
    xtest_path = await _project_file_path(db, project_id, xtest_file_id, "X test")
    ytest_path = await _project_file_path(db, project_id, ytest_file_id, "y test")
    clinical_path = await _project_file_path(db, project_id, clinical_file_id, "clinical data")

    config_dict = _prepare_config(config)

    # Compute config hash for duplicate detection (nulls stripped for stability)
    config_hash = _compute_config_hash(config_dict, {
        "x": x_file_id, "y": y_file_id,
        "xtest": xtest_file_id, "ytest": ytest_file_id,
    })

    # Create job record in database — commit immediately so the job runner
    # (which uses a separate sync DB connection) can see the job.
    job = Job(
        project_id=project_id, user_id=user.id, name=job_name or None,
        status="pending", config=config_dict, config_hash=config_hash,
    )
    db.add(job)
    await db.commit()

    job_dir = Path(storage.settings.project_dir) / project_id / "jobs" / job.id
    job_dir.mkdir(parents=True, exist_ok=True)

    param_path = engine.write_param_yaml(
        config=config_dict,
        x_path=str(x_path),
        y_path=str(y_path),
        xtest_path=xtest_path,
        ytest_path=ytest_path,
        clinical_path=clinical_path,
        output_dir=str(job_dir),
    )

    await audit.log_action(db, user, audit.ACTION_JOB_LAUNCH, "job", job.id,
                           details={"project_id": project_id})
    await db.commit()  # Ensure all writes are flushed before the job starts

    await _launch(job, project_id, param_path, job_dir, user, db, background_tasks)

    return ExperimentSummary(job_id=job.id, name=job.name, status=JobStatus.pending)


# ---------------------------------------------------------------------------
# Batch runs — parameter sweeps
# ---------------------------------------------------------------------------

def _sweep_target(key: str) -> tuple[str, str]:
    """Validate a sweep key ('section.param') against RunConfig; return (section, field)."""
    parts = key.split(".")
    if len(parts) != 2 or not all(parts):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid sweep parameter '{key}': expected 'section.parameter' (e.g. 'ga.population_size')",
        )
    section, param = parts
    section_field = RunConfig.model_fields.get(section)
    if section_field is None:
        raise HTTPException(status_code=422, detail=f"Unknown sweep section '{section}' in '{key}'")
    fields = section_field.annotation.model_fields
    for name, info in fields.items():
        if param == name or (info.alias and param == info.alias):
            return section, name
    raise HTTPException(status_code=422, detail=f"Unknown sweep parameter '{key}'")


def _apply_sweep(config_dict: dict, key: str, value) -> dict:
    """Apply a single sweep value to a config dict (e.g. 'ga.population_size' = 5000)."""
    section, param = _sweep_target(key)
    out = copy.deepcopy(config_dict)
    out.setdefault(section, {})[param] = value
    return out


def _validate_swept_config(cfg: dict, label: str) -> None:
    """Swept values go through the same bounds as a normal run."""
    try:
        RunConfig.model_validate(cfg)
    except ValidationError as e:
        first = e.errors()[0]
        loc = ".".join(str(p) for p in first.get("loc", ()))
        raise HTTPException(
            status_code=422,
            detail=f"Invalid sweep value ({label}): {loc}: {first.get('msg')}",
        )


@router.post("/{project_id}/batch", response_model=BatchLaunch, response_model_exclude_unset=True)
async def run_batch(
    project_id: str,
    config: RunConfig,
    sweep: BatchSweepConfig,
    x_file_id: str,
    y_file_id: str,
    xtest_file_id: str = "",
    ytest_file_id: str = "",
    clinical_file_id: str = "",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    """Launch a batch of jobs from parameter sweeps (editor access required).

    The sweep config defines which parameters to vary. A cartesian product
    of all sweep values is computed, and one job is created per combination.
    Max 50 jobs per batch. Unknown parameters or out-of-range values are
    rejected (422) before any job is created.
    """
    await get_project_access(project_id, user, db, require_role="editor")

    if not sweep.sweeps:
        raise HTTPException(status_code=400, detail="No sweep parameters defined")

    keys = list(sweep.sweeps.keys())
    for k in keys:
        _sweep_target(k)
        if not sweep.sweeps[k]:
            raise HTTPException(status_code=422, detail=f"Sweep parameter '{k}' has no values")

    # Build cartesian product of sweep values
    values = [sweep.sweeps[k] for k in keys]
    n_combinations = 1
    for v in values:
        n_combinations *= len(v)
    if n_combinations > MAX_BATCH_JOBS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many combinations ({n_combinations}). Maximum is {MAX_BATCH_JOBS}.",
        )
    combinations = list(itertools.product(*values))

    # Resolve file paths — every file must belong to a dataset of this project
    x_path = await _project_file_path(db, project_id, x_file_id, "X train")
    y_path = await _project_file_path(db, project_id, y_file_id, "y train")
    if not x_path or not y_path:
        raise HTTPException(status_code=404, detail="Dataset file not found")
    xtest_path = await _project_file_path(db, project_id, xtest_file_id, "X test")
    ytest_path = await _project_file_path(db, project_id, ytest_file_id, "y test")
    clinical_path = await _project_file_path(db, project_id, clinical_file_id, "clinical data")

    batch_id = uuid.uuid4().hex[:12]
    base_config = _prepare_config(config)

    # Build and validate every configuration before creating anything.
    planned = []
    for combo in combinations:
        cfg = base_config
        name_parts = []
        for key, val in zip(keys, combo):
            cfg = _apply_sweep(cfg, key, val)
            name_parts.append(f"{key.split('.')[-1]}={val}")
        label = " ".join(name_parts)
        _validate_swept_config(cfg, label)
        planned.append((_prepare_config(cfg, label), f"[Batch] {label}"))

    launches = []
    for cfg, job_name in planned:
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
            clinical_path=clinical_path,
            output_dir=str(job_dir),
        )
        launches.append((job, param_path, job_dir))

    await db.commit()

    # One independent task per job: a failure of one cannot strand the others.
    for job, param_path, job_dir in launches:
        await _launch(job, project_id, param_path, job_dir, user, db, background_tasks)

    return {
        "batch_id": batch_id,
        "job_count": len(launches),
        "jobs": [{"job_id": j.id, "name": j.name} for j, _, _ in launches],
    }


@router.get("/{project_id}/batches", response_model=List[BatchSummary], response_model_exclude_unset=True)
async def list_batches(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all batch runs for a project with summary stats."""
    await get_project_access(project_id, user, db, require_role="viewer")

    result = await db.execute(
        select(Job)
        .where(Job.project_id == project_id, Job.batch_id.isnot(None))
        .order_by(Job.created_at.desc())
    )
    batch_rows = result.scalars().all()

    batches: dict[str, list[Job]] = {}
    for j in batch_rows:
        batches.setdefault(j.batch_id, []).append(j)

    summaries = []
    for bid, batch_jobs in batches.items():
        completed = [j for j in batch_jobs if j.status == "completed"]
        best_auc = None
        best_job_id = None
        for j in completed:
            auc = j.best_auc
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


@router.get("/{project_id}/jobs/duplicates", response_model=List[DuplicateGroup], response_model_exclude_unset=True)
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
    await get_project_access(project_id, user, db, require_role="viewer")

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
            auc = j.best_auc or 0.0
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


@router.get("/{project_id}/jobs/{job_id}/config", response_model=JobConfigResponse, response_model_exclude_unset=True)
async def get_job_config(
    project_id: str,
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the full configuration of a job (viewer access).

    Returns the RunConfig dict stored when the job was created,
    so the frontend can pre-fill the Parameters tab for a duplicate run.
    """
    job = await _verify_job_access(project_id, job_id, user, db)
    return {
        "job_id": job_id,
        "name": job.name,
        "config": job.config or {},
    }


@router.post("/{project_id}/jobs/{job_id}/rerun", response_model=ExperimentSummary)
async def rerun_job(
    project_id: str,
    job_id: str,
    job_name: str = "",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    """Re-run a job with the same configuration (editor access required).

    Creates a new job with the original job's config and the same data files
    (409 if they were removed from the project). Useful for reproducibility testing.
    """
    await get_project_access(project_id, user, db, require_role="editor")

    # Load original job
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.project_id == project_id)
    )
    original = result.scalar_one_or_none()
    if not original:
        raise HTTPException(status_code=404, detail="Job not found")
    if not original.config:
        raise HTTPException(status_code=400, detail="Job has no stored configuration")

    # Re-use the exact files of the original job (not the project's latest
    # uploads: a project can hold several datasets, e.g. one per CV split).
    file_map = await _original_job_files(db, project_id, original.id)
    xtrain, ytrain = file_map["X"], file_map["y"]
    xtest_file, ytest_file = file_map["Xtest"], file_map["ytest"]
    x_path, y_path = xtrain.disk_path, ytrain.disk_path
    xtest_path = xtest_file.disk_path if xtest_file else ""
    ytest_path = ytest_file.disk_path if ytest_file else ""
    clinical_path = file_map["clinical"].disk_path if file_map["clinical"] else ""

    config_dict = _prepare_config(original.config)
    config_hash = _compute_config_hash(config_dict, {
        "x": xtrain.id, "y": ytrain.id,
        "xtest": xtest_file.id if xtest_file else "",
        "ytest": ytest_file.id if ytest_file else "",
    })

    # Generate rerun name
    rerun_name = job_name or f"[Rerun] {original.name or original.id[:8]}"

    job = Job(
        project_id=project_id, user_id=user.id, name=rerun_name,
        status="pending", config=config_dict, config_hash=config_hash,
    )
    db.add(job)
    await db.commit()

    job_dir = Path(storage.settings.project_dir) / project_id / "jobs" / job.id
    job_dir.mkdir(parents=True, exist_ok=True)

    param_path = engine.write_param_yaml(
        config=config_dict,
        x_path=str(x_path),
        y_path=str(y_path),
        xtest_path=xtest_path,
        ytest_path=ytest_path,
        clinical_path=clinical_path,
        output_dir=str(job_dir),
    )

    await audit.log_action(db, user, audit.ACTION_JOB_LAUNCH, "job", job.id,
                           details={"project_id": project_id, "rerun_of": job_id})
    await db.commit()

    await _launch(job, project_id, param_path, job_dir, user, db, background_tasks)

    return ExperimentSummary(job_id=job.id, name=job.name, status=JobStatus.pending)


@router.get("/{project_id}/jobs/{job_id}/logs", response_model=JobLogs, response_model_exclude_unset=True)
async def get_job_logs(
    project_id: str,
    job_id: str,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the console log output for a job (viewer access).

    Without ``offset`` the log is returned whole, or only its last megabyte if
    it is larger (``truncated`` is then true). To follow a running job cheaply,
    pass the ``next_offset`` of the previous response as ``offset``: only the
    new output is returned.
    """
    job = await _verify_job_access(project_id, job_id, user, db)

    log_path = results_io.job_dir(project_id, job_id) / "console.log"
    chunk = await asyncio.to_thread(results_io.read_log_chunk, log_path, max(0, offset))

    return {
        "job_id": job_id,
        "status": job.status,
        "log": chunk["log"],
        "size": chunk["size"],
        "offset": chunk["offset"],
        "next_offset": chunk["next_offset"],
        "truncated": chunk["truncated"],
    }


def _read_progress(project_id: str, job_id: str) -> dict:
    progress_path = results_io.job_dir(project_id, job_id) / "progress.json"
    try:
        return json.loads(progress_path.read_text())
    except (OSError, ValueError):
        return {"max_gen": 0, "points": []}


@router.get("/{project_id}/jobs/{job_id}/progress", response_model=JobProgress, response_model_exclude_unset=True)
async def get_job_progress(
    project_id: str,
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get structured progress data for a running job."""
    await _verify_job_access(project_id, job_id, user, db)
    return await asyncio.to_thread(_read_progress, project_id, job_id)


@router.post("/{project_id}/jobs/{job_id}/cancel", response_model=ExperimentSummary)
async def cancel_job(
    project_id: str,
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stop a pending or running job (editor access required).

    The worker process is terminated and the job ends with status ``failed`` and
    the error message "Cancelled by user.". Cancelling a finished job is a 409.
    """
    await get_project_access(project_id, user, db, require_role="editor")
    result = await db.execute(
        select(Job).options(selectinload(Job.owner)).where(Job.id == job_id, Job.project_id == project_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("pending", "running"):
        raise HTTPException(status_code=409, detail=f"Job is already {job.status}")

    was_running = job.status == "running"
    tracked = jobs.cancel(job_id)
    if not (tracked and was_running):
        # Queued (the runner will skip it) or orphaned (no live worker): close it here.
        job.status = "failed"
        job.error_message = jobs.CANCELLED_MESSAGE
        job.completed_at = datetime.now(timezone.utc)
        job.pid = None
    else:
        # The runner thread records the final state once the worker has exited;
        # report it as cancelled right away.
        job.error_message = jobs.CANCELLED_MESSAGE
    await audit.log_action(db, user, "job.cancel", "job", job_id,
                           details={"project_id": project_id})
    await db.commit()
    return _job_to_summary(job)


@router.get("/{project_id}/jobs/{job_id}", response_model=ExperimentSummary)
async def get_job_status(
    project_id: str,
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the status of a running or completed job (viewer access)."""
    await get_project_access(project_id, user, db, require_role="viewer")
    result = await db.execute(
        select(Job).options(selectinload(Job.owner)).where(Job.id == job_id, Job.project_id == project_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == "completed" and job.results_path:
        # summary.json is a few hundred bytes; the full results are not re-parsed on each poll
        summary = await asyncio.to_thread(results_io.load_summary, project_id, job_id)
        if summary:
            return _job_to_summary(job, summary)

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

    results = await results_io.aload_results(project_id, job_id)
    if not results:
        raise HTTPException(status_code=404, detail="Results not found")

    best = results.get("best_individual", {})
    tracking = results.get("generation_tracking") or []
    test_auc = tracking[-1].get("best_auc_test") if tracking and isinstance(tracking[-1], dict) else None
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
        best_auc_test=test_auc if isinstance(test_auc, (int, float)) and test_auc > 0 else None,
        feature_names=results.get("feature_names", []),
        sample_names=results.get("sample_names", []),
        best_individual=IndividualResponse(**best) if best else None,
        mock=bool(results.get("mock")) or None,
    )


@router.get("/{project_id}/jobs/{job_id}/results", response_model=JobResults, response_model_exclude_unset=True)
async def get_job_results_raw(
    project_id: str,
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full results JSON including population and generation tracking (viewer access)."""
    await _verify_job_access(project_id, job_id, user, db)

    results = await results_io.aload_results(project_id, job_id)
    if not results:
        raise HTTPException(status_code=404, detail="Results not found")

    return results


@router.get("/{project_id}/jobs/{job_id}/stability", response_model=StabilityAnalysis, response_model_exclude_unset=True)
async def get_stability_analysis(
    project_id: str,
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return model stability analysis for a job's FBM population.

    Serves pre-computed data from results when available (fast path).
    Falls back to on-demand computation for legacy results.
    """
    await _verify_job_access(project_id, job_id, user, db)
    results = await results_io.aload_results(project_id, job_id)
    if not results:
        raise HTTPException(status_code=404, detail="Results not found")

    # Fast path: serve pre-computed stability data
    if "stability" in results:
        return results["stability"]

    # Fallback: compute on-demand for legacy results without pre-computed data
    from ..services import stability

    population = results.get("population", [])
    feature_names = results.get("feature_names", [])
    if not population:
        raise HTTPException(status_code=400, detail="No population data in results")

    return await asyncio.to_thread(stability.compute_stability_analysis, population, feature_names)


@router.post("/{project_id}/jobs/{job_id}/validate", response_model=ValidationResult, response_model_exclude_unset=True)
async def validate_on_new_data(
    project_id: str,
    job_id: str,
    x_file: UploadFile = File(..., description="Feature matrix TSV"),
    y_file: UploadFile = File(None, description="Optional class labels TSV"),
    features_in_rows: bool = Form(True),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Score new samples against a trained model (viewer access).

    Upload an X matrix (TSV) and optionally Y labels to compute predictions
    and evaluation metrics using the best model from a completed job.
    """
    job = await _verify_job_access(project_id, job_id, user, db)
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")

    results = await results_io.aload_results(project_id, job_id)
    if not results:
        raise HTTPException(status_code=404, detail="Results not found")

    x_content = await read_upload(x_file)
    y_content = await read_upload(y_file) if y_file is not None else None

    def _score() -> dict:
        try:
            x_data = parse_tsv(x_content)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Failed to parse X file: {e}")
        y_labels = None
        if y_content is not None:
            try:
                y_labels = parse_tsv(y_content).iloc[:, 0]
            except Exception as e:  # noqa: BLE001
                raise HTTPException(status_code=400, detail=f"Failed to parse Y file: {e}")
        try:
            return predict_from_model(
                results, x_data, y_labels=y_labels, features_in_rows=features_in_rows,
            )
        except UnsupportedModelError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:  # noqa: BLE001
            logger.exception("Prediction failed for job %s", job_id)
            raise HTTPException(status_code=500, detail=f"Prediction failed: {e}")

    return await asyncio.to_thread(_score)


@router.get("/{project_id}/jobs", response_model=List[ExperimentSummary])
async def list_jobs(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all jobs for a project (viewer access)."""
    await get_project_access(project_id, user, db, require_role="viewer")

    result = await db.execute(
        select(Job)
        .options(selectinload(Job.owner))
        .where(Job.project_id == project_id)
        .order_by(Job.created_at.desc())
    )
    job_rows = result.scalars().all()

    # Backfill missing cached columns for older jobs (file work in a thread)
    dirty = False
    for j in job_rows:
        if j.config_hash is None and j.config:
            j.config_hash = _compute_config_hash(j.config)
            dirty = True
        if j.disk_size_bytes is None and j.status == "completed":
            j.disk_size_bytes = await asyncio.to_thread(jobs.job_disk_size, j.project_id, j.id)
            dirty = True
        # Lazy backfill best_auc/best_k from the job summary if not cached yet
        if j.status == "completed" and j.best_auc is None:
            summary = await asyncio.to_thread(results_io.load_summary, project_id, j.id)
            if summary and summary.get("best_auc") is not None:
                j.best_auc = summary.get("best_auc")
                j.best_k = summary.get("best_k")
                dirty = True
    if dirty:
        await db.commit()

    # All data now comes from DB — no per-job file reads needed
    return [_job_to_summary(j) for j in job_rows]


@router.delete("/{project_id}/jobs/{job_id}", response_model=Detail, response_model_exclude_unset=True)
async def delete_job(
    project_id: str,
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a job and its results (editor access required)."""
    await get_project_access(project_id, user, db, require_role="editor")
    job = await _verify_job_access(project_id, job_id, user, db)

    if job.status == "running" and jobs.is_tracked(job_id):
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a running job — cancel it first",
        )
    # Queued jobs are skipped by the runner; a "running" job that no worker
    # owns any more (left over from a restart) can simply be removed.
    if job.status in ("pending", "running"):
        jobs.cancel(job_id)

    await audit.log_action(db, user, audit.ACTION_JOB_DELETE, "job", job_id,
                           details={"project_id": project_id})

    await db.execute(sa_delete(Job).where(Job.id == job_id))
    await db.commit()

    # Remove files only once the database row is gone
    job_dir = results_io.job_dir(project_id, job_id)
    if job_dir.exists():
        await asyncio.to_thread(shutil.rmtree, job_dir, True)
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


def _aware(dt: datetime) -> datetime:
    """Datetimes read back from SQLite are naive UTC; make them comparable."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _job_to_summary(job: Job, summary: dict | None = None) -> ExperimentSummary:
    """Convert a Job ORM object to an ExperimentSummary.

    Uses cached best_auc/best_k from DB columns — no file I/O needed. ``summary``
    (the job's summary.json) adds the result dimensions for completed jobs.
    """
    config = job.config or {}
    gen = config.get("general", {})
    ga = config.get("ga", {})
    summary = summary or {}
    started = getattr(job, "started_at", None)
    duration = None
    # Run time, not queue time: measured from the moment the worker started.
    begin = started or job.created_at
    if job.completed_at and begin:
        duration = max(0.0, (_aware(job.completed_at) - _aware(begin)).total_seconds())
    return ExperimentSummary(
        job_id=job.id,
        name=job.name,
        status=JobStatus(job.status),
        fold_count=summary.get("fold_count") or 0,
        generation_count=summary.get("generation_count") or 0,
        execution_time=summary.get("execution_time") or 0.0,
        feature_count=summary.get("feature_count") or 0,
        sample_count=summary.get("sample_count") or 0,
        best_auc=summary.get("best_auc") if summary.get("best_auc") is not None else job.best_auc,
        best_k=summary.get("best_k") if summary.get("best_k") is not None else job.best_k,
        created_at=job.created_at.isoformat() if job.created_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        duration_seconds=duration,
        config_summary=_config_summary(config),
        user_name=job.owner.full_name if job.owner and job.owner.full_name else (job.owner.email if job.owner else None),
        language=gen.get("language"),
        data_type=gen.get("data_type"),
        population_size=ga.get("population_size"),
        config_hash=job.config_hash,
        disk_size_bytes=job.disk_size_bytes,
        batch_id=job.batch_id,
        error_message=job.error_message,
        started_at=started.isoformat() if started else None,
        mock=True if summary.get("mock") else None,
    )
