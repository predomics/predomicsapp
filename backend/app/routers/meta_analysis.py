"""Multi-cohort meta-analysis — compare models across projects."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import get_current_user, get_project_with_access
from ..models.db_models import User, Project, Job, ProjectShare
from ..services import results_io
from typing import List
from ..models.schemas import (
    MetaComparison, SearchableJob,
)

router = APIRouter(prefix="/meta-analysis", tags=["meta-analysis"])


class MetaAnalysisRequest(BaseModel):
    job_ids: list[str] = Field(..., min_length=2, max_length=10)


@router.get("/searchable-jobs", response_model=List[SearchableJob], response_model_exclude_unset=True)
async def list_searchable_jobs(
    q: str = Query("", description="Search filter on project/job name"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all completed jobs the user can access (for job picker)."""

    # Own projects + shared projects (reuse dashboard pattern)
    own_project_ids = select(Project.id).where(Project.user_id == user.id)
    shared_project_ids = select(ProjectShare.project_id).where(ProjectShare.user_id == user.id)
    all_project_ids = own_project_ids.union(shared_project_ids)

    stmt = (
        select(Job, Project.name.label("project_name"))
        .join(Project, Job.project_id == Project.id)
        .where(
            Job.project_id.in_(all_project_ids),
            Job.status == "completed",
        )
    )

    if q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Project.name.ilike(pattern),
                Job.name.ilike(pattern),
            )
        )

    stmt = stmt.order_by(Job.completed_at.desc()).limit(50)
    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "job_id": job.id,
            "project_id": job.project_id,
            "project_name": project_name,
            "job_name": job.name,
            "best_auc": job.best_auc,
            "best_k": job.best_k,
            "language": ((job.config or {}).get("general") or {}).get("language"),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }
        for job, project_name in rows
    ]


@router.post("/compare", response_model=MetaComparison, response_model_exclude_unset=True)
async def compare_jobs(
    body: MetaAnalysisRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compare models across jobs (cross-project meta-analysis)."""

    jobs_data = []

    for job_id in body.job_ids:
        # Load job
        result = await db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(404, f"Job {job_id} not found")

        # Verify access
        try:
            project, _role = await get_project_with_access(
                job.project_id, user, db, require_role="viewer"
            )
        except HTTPException:
            raise HTTPException(403, f"No access to job {job_id}")

        # Load results
        results = await results_io.aload_results(job.project_id, job_id)
        if not results:
            raise HTTPException(404, f"Results not found for job {job_id}")

        best = results.get("best_individual", {})
        feature_names = results.get("feature_names", [])

        # Build named features with coefficients
        named_features = {}
        for idx_str, coef in (best.get("features") or {}).items():
            idx = int(idx_str)
            name = feature_names[idx] if idx < len(feature_names) else f"feature_{idx}"
            named_features[name] = float(coef)

        jobs_data.append({
            "job_id": job_id,
            "project_id": job.project_id,
            "project_name": project.name,
            "job_name": job.name,
            "best_auc": best.get("auc"),
            "best_k": best.get("k"),
            "language": best.get("language"),
            "data_type": best.get("data_type"),
            "accuracy": best.get("accuracy"),
            "sensitivity": best.get("sensitivity"),
            "specificity": best.get("specificity"),
            "named_features": named_features,
        })

    # Compute feature overlap
    feature_jobs = {}
    for jd in jobs_data:
        for fname in jd["named_features"]:
            feature_jobs.setdefault(fname, []).append(jd["job_id"])

    # Compute concordance (sign agreement across jobs)
    concordance = {}
    for fname, jids in feature_jobs.items():
        pos_jobs = []
        neg_jobs = []
        for jd in jobs_data:
            coef = jd["named_features"].get(fname)
            if coef is not None:
                if coef > 0:
                    pos_jobs.append(jd["job_id"])
                else:
                    neg_jobs.append(jd["job_id"])
        concordance[fname] = {
            "positive_jobs": pos_jobs,
            "negative_jobs": neg_jobs,
            "concordant": len(pos_jobs) == 0 or len(neg_jobs) == 0,
        }

    # Compute meta-AUC (weighted average by sample count or equal weight)
    aucs = [jd["best_auc"] for jd in jobs_data if jd["best_auc"] is not None]
    meta_auc = sum(aucs) / len(aucs) if aucs else None

    return {
        "jobs": jobs_data,
        "feature_overlap": feature_jobs,
        "concordance": concordance,
        "meta_auc": meta_auc,
    }
