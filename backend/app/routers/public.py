"""Public sharing — read-only access via unique token URLs."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import get_current_user, get_project_with_access
from ..models.db_models import User, Project, Job, PublicShare
from ..services import storage

router = APIRouter(tags=["public"])


class CreatePublicShareRequest(BaseModel):
    expires_in_days: Optional[int] = None  # None = never expires


# ---------------------------------------------------------------------------
# Authenticated endpoints (manage links)
# ---------------------------------------------------------------------------

@router.post("/projects/{project_id}/public")
async def create_public_link(
    project_id: str,
    body: CreatePublicShareRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a public share link (project owner only)."""
    project = await get_project_with_access(project_id, user, db, require_role="editor")
    if project.user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the project owner can create public links")

    token = secrets.token_urlsafe(48)
    expires_at = None
    if body.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_in_days)

    share = PublicShare(
        project_id=project_id,
        token=token,
        created_by=user.id,
        expires_at=expires_at,
    )
    db.add(share)
    await db.commit()
    await db.refresh(share)

    return {
        "id": share.id,
        "token": share.token,
        "expires_at": share.expires_at.isoformat() if share.expires_at else None,
        "created_at": share.created_at.isoformat() if share.created_at else None,
        "is_active": share.is_active,
    }


@router.get("/projects/{project_id}/public")
async def list_public_links(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all public share links for a project (owner only)."""
    project = await get_project_with_access(project_id, user, db, require_role="editor")
    if project.user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the project owner can view public links")

    result = await db.execute(
        select(PublicShare)
        .where(PublicShare.project_id == project_id)
        .order_by(PublicShare.created_at.desc())
    )
    shares = result.scalars().all()

    return [
        {
            "id": s.id,
            "token": s.token,
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "is_active": s.is_active,
        }
        for s in shares
    ]


@router.delete("/projects/{project_id}/public/{share_id}")
async def revoke_public_link(
    project_id: str,
    share_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a public share link (owner only)."""
    project = await get_project_with_access(project_id, user, db, require_role="editor")
    if project.user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the project owner can revoke links")

    result = await db.execute(
        select(PublicShare).where(
            PublicShare.id == share_id,
            PublicShare.project_id == project_id,
        )
    )
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share link not found")

    await db.delete(share)
    await db.commit()
    return {"detail": "Link revoked"}


# ---------------------------------------------------------------------------
# Unauthenticated public endpoints
# ---------------------------------------------------------------------------

async def _get_valid_share(token: str, db: AsyncSession) -> PublicShare:
    """Fetch and validate a public share by token."""
    result = await db.execute(
        select(PublicShare).where(PublicShare.token == token, PublicShare.is_active.is_(True))
    )
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share link not found or revoked")

    if share.expires_at and share.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Share link has expired")

    return share


@router.get("/public/{token}")
async def get_public_project(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Get project info and completed jobs via public token (no auth required)."""
    share = await _get_valid_share(token, db)

    # Get project
    result = await db.execute(
        select(Project).where(Project.id == share.project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get completed jobs
    result = await db.execute(
        select(Job)
        .where(Job.project_id == share.project_id, Job.status == "completed")
        .order_by(Job.completed_at.desc())
    )
    jobs = result.scalars().all()

    return {
        "project": {
            "name": project.name,
            "description": project.description,
        },
        "jobs": [
            {
                "job_id": j.id,
                "name": j.name,
                "best_auc": j.best_auc,
                "best_k": j.best_k,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            }
            for j in jobs
        ],
    }


@router.get("/public/{token}/jobs/{job_id}/results")
async def get_public_job_results(
    token: str,
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get full job results via public token (no auth required)."""
    share = await _get_valid_share(token, db)

    result = await db.execute(
        select(Job).where(
            Job.id == job_id,
            Job.project_id == share.project_id,
            Job.status == "completed",
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    results = storage.get_job_result(share.project_id, job_id)
    if not results:
        raise HTTPException(status_code=404, detail="Results not found")

    return results
