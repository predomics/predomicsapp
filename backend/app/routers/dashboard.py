"""Dashboard endpoint — global summary stats and recent activity."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import get_current_user
from ..models.db_models import User, Project, Dataset, Job, ProjectShare, AuditLog

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/")
async def get_dashboard(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return dashboard summary for the current user."""

    uid = user.id

    # Count own projects
    r = await db.execute(
        select(func.count()).select_from(Project).where(Project.user_id == uid)
    )
    project_count = r.scalar() or 0

    # Count shared-with-me projects
    r = await db.execute(
        select(func.count()).select_from(ProjectShare).where(ProjectShare.user_id == uid)
    )
    shared_count = r.scalar() or 0

    # Count own datasets
    r = await db.execute(
        select(func.count()).select_from(Dataset).where(Dataset.user_id == uid)
    )
    dataset_count = r.scalar() or 0

    # Job counts (across own + shared projects)
    own_project_ids = select(Project.id).where(Project.user_id == uid)
    shared_project_ids = select(ProjectShare.project_id).where(ProjectShare.user_id == uid)
    all_project_ids = own_project_ids.union(shared_project_ids)

    job_counts = {}
    for status_val in ["running", "pending", "completed", "failed"]:
        r = await db.execute(
            select(func.count()).select_from(Job).where(
                Job.project_id.in_(all_project_ids),
                Job.status == status_val,
            )
        )
        job_counts[status_val] = r.scalar() or 0

    # Active jobs (running/pending) with details
    r = await db.execute(
        select(Job)
        .where(
            Job.project_id.in_(all_project_ids),
            Job.status.in_(["running", "pending"]),
        )
        .order_by(Job.created_at.desc())
        .limit(10)
    )
    active_jobs_raw = r.scalars().all()
    active_jobs = []
    for j in active_jobs_raw:
        active_jobs.append({
            "job_id": j.id,
            "project_id": j.project_id,
            "name": j.name,
            "status": j.status,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        })

    # Recent completions (last 10)
    r = await db.execute(
        select(Job)
        .where(
            Job.project_id.in_(all_project_ids),
            Job.status == "completed",
        )
        .order_by(Job.completed_at.desc())
        .limit(10)
    )
    recent_raw = r.scalars().all()
    recent_completions = []
    for j in recent_raw:
        recent_completions.append({
            "job_id": j.id,
            "project_id": j.project_id,
            "name": j.name,
            "best_auc": j.best_auc,
            "best_k": j.best_k,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        })

    # Recent activity (last 20 audit log entries for this user)
    r = await db.execute(
        select(AuditLog)
        .where(AuditLog.user_id == uid)
        .order_by(AuditLog.created_at.desc())
        .limit(20)
    )
    activity_raw = r.scalars().all()
    activity = []
    for a in activity_raw:
        activity.append({
            "action": a.action,
            "resource_type": a.resource_type,
            "resource_id": a.resource_id,
            "details": a.details,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })

    return {
        "projects": project_count,
        "shared_with_me": shared_count,
        "datasets": dataset_count,
        "running_jobs": job_counts["running"],
        "pending_jobs": job_counts["pending"],
        "completed_jobs": job_counts["completed"],
        "failed_jobs": job_counts["failed"],
        "active_jobs": active_jobs,
        "recent_completions": recent_completions,
        "activity": activity,
    }
