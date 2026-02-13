"""Analysis execution endpoints — run gpredomics and retrieve results."""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db, async_session_factory
from ..core.deps import get_current_user
from ..models.db_models import User, Project, Job
from ..models.schemas import (
    RunConfig,
    ExperimentSummary,
    ExperimentDetail,
    IndividualResponse,
    JobStatus,
)
from ..services import engine, storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/{project_id}/run", response_model=ExperimentSummary)
async def run_analysis(
    project_id: str,
    config: RunConfig,
    x_dataset_id: str,
    y_dataset_id: str,
    xtest_dataset_id: str = "",
    ytest_dataset_id: str = "",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    """Launch a gpredomics analysis run."""
    # Verify project ownership
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    # Resolve dataset paths
    x_path = storage.get_dataset_path(project_id, x_dataset_id)
    y_path = storage.get_dataset_path(project_id, y_dataset_id)
    if not x_path or not y_path:
        raise HTTPException(status_code=404, detail="Dataset not found")

    xtest_path = ""
    ytest_path = ""
    if xtest_dataset_id:
        p = storage.get_dataset_path(project_id, xtest_dataset_id)
        xtest_path = str(p) if p else ""
    if ytest_dataset_id:
        p = storage.get_dataset_path(project_id, ytest_dataset_id)
        ytest_path = str(p) if p else ""

    # Create job record in database
    job = Job(project_id=project_id, status="pending", config=config.model_dump())
    db.add(job)
    await db.flush()

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

    return ExperimentSummary(job_id=job.id, status=JobStatus.pending)


def _run_job(job_id: str, project_id: str, param_path: str) -> None:
    """Execute gpredomics in a subprocess so we can capture Rust stdout."""
    import asyncio
    import subprocess
    import sys

    job_dir = Path(storage.settings.project_dir) / project_id / "jobs" / job_id
    log_path = job_dir / "console.log"
    results_path = job_dir / "results.json"

    async def _execute():
        # Mark job as running
        async with async_session_factory() as db:
            result = await db.execute(select(Job).where(Job.id == job_id))
            job = result.scalar_one()
            job.status = "running"
            await db.commit()

        try:
            if not engine.HAS_ENGINE:
                # Mock mode — no subprocess needed
                mock_results = engine._mock_results()
                storage.save_job_result(project_id, job_id, mock_results)
                with open(log_path, "w") as lf:
                    lf.write("[mock] Engine not available, using mock results\n")

                async with async_session_factory() as db:
                    result = await db.execute(select(Job).where(Job.id == job_id))
                    job = result.scalar_one()
                    job.status = "completed"
                    job.results_path = str(results_path)
                    job.completed_at = datetime.now(timezone.utc)
                    await db.commit()
                return

            # Run worker subprocess — captures all Rust stdout
            worker_module = "app.services.worker"
            with open(log_path, "w") as lf:
                proc = subprocess.Popen(
                    [sys.executable, "-m", worker_module, param_path, str(results_path)],
                    stdout=lf,
                    stderr=subprocess.STDOUT,
                    cwd=str(Path(__file__).resolve().parents[2]),  # backend/
                )
                proc.wait()

            if proc.returncode != 0:
                error_msg = log_path.read_text()[-500:] if log_path.exists() else "Unknown error"
                raise RuntimeError(f"Worker exited with code {proc.returncode}: {error_msg}")

            async with async_session_factory() as db:
                result = await db.execute(select(Job).where(Job.id == job_id))
                job = result.scalar_one()
                job.status = "completed"
                job.results_path = str(results_path)
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()

            logger.info("Job %s completed", job_id)

        except Exception as e:
            # Append error to log
            with open(log_path, "a") as lf:
                lf.write(f"\n[error] {e}\n")

            async with async_session_factory() as db:
                result = await db.execute(select(Job).where(Job.id == job_id))
                job = result.scalar_one()
                job.status = "failed"
                job.error_message = str(e)
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()

            logger.error("Job %s failed: %s", job_id, e)

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_execute())
    finally:
        loop.close()


@router.get("/{project_id}/jobs/{job_id}/logs")
async def get_job_logs(
    project_id: str,
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the console log output for a job."""
    result = await db.execute(
        select(Job).join(Project).where(
            Job.id == job_id,
            Job.project_id == project_id,
            Project.user_id == user.id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

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
    """Get the status of a running or completed job."""
    result = await db.execute(
        select(Job).join(Project).where(
            Job.id == job_id,
            Job.project_id == project_id,
            Project.user_id == user.id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == "completed" and job.results_path:
        results = storage.get_job_result(project_id, job_id)
        if results:
            return _results_to_summary(job_id, JobStatus(job.status), results)

    return ExperimentSummary(job_id=job_id, status=JobStatus(job.status))


@router.get("/{project_id}/jobs/{job_id}/detail", response_model=ExperimentDetail)
async def get_job_detail(
    project_id: str,
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed results of a completed job."""
    result = await db.execute(
        select(Job).join(Project).where(
            Job.id == job_id,
            Job.project_id == project_id,
            Project.user_id == user.id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or not completed")

    results = storage.get_job_result(project_id, job_id)
    if not results:
        raise HTTPException(status_code=404, detail="Results not found")

    best = results.get("best_individual", {})
    return ExperimentDetail(
        job_id=job_id,
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


@router.get("/{project_id}/jobs")
async def list_jobs(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all jobs for a project."""
    result = await db.execute(
        select(Job).join(Project).where(
            Job.project_id == project_id,
            Project.user_id == user.id,
        ).order_by(Job.created_at.desc())
    )
    jobs = result.scalars().all()

    summaries = []
    for j in jobs:
        if j.status == "completed":
            results = storage.get_job_result(project_id, j.id)
            if results:
                summaries.append(_results_to_summary(j.id, JobStatus.completed, results))
                continue
        summaries.append(ExperimentSummary(job_id=j.id, status=JobStatus(j.status)))
    return summaries


def _results_to_summary(job_id: str, status: JobStatus, results: dict) -> ExperimentSummary:
    best = results.get("best_individual", {})
    return ExperimentSummary(
        job_id=job_id,
        status=status,
        fold_count=results.get("fold_count", 0),
        generation_count=results.get("generation_count", 0),
        execution_time=results.get("execution_time", 0),
        feature_count=len(results.get("feature_names", [])),
        sample_count=len(results.get("sample_names", [])),
        best_auc=best.get("auc"),
        best_k=best.get("k"),
    )
