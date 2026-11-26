"""Project sharing endpoints — share projects with other users."""

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.deps import get_current_user, get_project_access
from ..models.db_models import User, Project, ProjectShare
from ..services import audit
from ..models.api_schemas import ShareUpdated, StatusOut, SharedProjectOut

router = APIRouter(prefix="/projects", tags=["sharing"])


class ShareRequest(BaseModel):
    email: str
    role: str = "viewer"  # viewer or editor


class ShareResponse(BaseModel):
    id: str
    user_id: str
    email: str
    full_name: str
    role: str
    shared_at: str


@router.post("/{project_id}/share", response_model=ShareResponse)
async def share_project(
    project_id: str,
    body: ShareRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Share a project with another user (owner only)."""
    project, _ = await get_project_access(project_id, user, db, require_role="owner")

    if body.role not in ("viewer", "editor"):
        raise HTTPException(status_code=422, detail="Role must be 'viewer' or 'editor'")

    # Find target user
    result = await db.execute(
        select(User).where(func.lower(User.email) == (body.email or "").strip().lower())
    )
    target = result.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="Cannot share with yourself")

    # Check if already shared
    existing = await db.execute(
        select(ProjectShare).where(
            ProjectShare.project_id == project_id,
            ProjectShare.user_id == target.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already shared with this user")

    share = ProjectShare(
        project_id=project_id,
        user_id=target.id,
        role=body.role,
        shared_by=user.id,
    )
    db.add(share)
    await db.flush()
    await audit.log_action(db, user, audit.ACTION_SHARE_CREATE, "project", project_id, details={"email": target.email, "role": body.role})

    return ShareResponse(
        id=share.id,
        user_id=target.id,
        email=target.email,
        full_name=target.full_name,
        role=share.role,
        shared_at=share.shared_at.isoformat(),
    )


@router.get("/{project_id}/shares", response_model=list[ShareResponse])
async def list_shares(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all shares for a project (owner only)."""
    project, _ = await get_project_access(project_id, user, db, require_role="owner")

    result = await db.execute(
        select(ProjectShare)
        .where(ProjectShare.project_id == project_id)
        .options(selectinload(ProjectShare.user))
    )
    shares = result.scalars().all()
    return [
        ShareResponse(
            id=s.id,
            user_id=s.user_id,
            email=s.user.email,
            full_name=s.user.full_name,
            role=s.role,
            shared_at=s.shared_at.isoformat(),
        )
        for s in shares
    ]


@router.put("/{project_id}/shares/{share_id}", response_model=ShareUpdated)
async def update_share(
    project_id: str,
    share_id: str,
    body: ShareRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the role of a share (owner only)."""
    await get_project_access(project_id, user, db, require_role="owner")

    if body.role not in ("viewer", "editor"):
        raise HTTPException(status_code=422, detail="Role must be 'viewer' or 'editor'")

    result = await db.execute(
        select(ProjectShare).where(ProjectShare.id == share_id, ProjectShare.project_id == project_id)
    )
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    share.role = body.role
    return {"status": "updated", "role": body.role}


@router.delete("/{project_id}/shares/{share_id}", response_model=StatusOut)
async def revoke_share(
    project_id: str,
    share_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a share (owner only)."""
    await get_project_access(project_id, user, db, require_role="owner")

    result = await db.execute(
        select(ProjectShare).where(ProjectShare.id == share_id, ProjectShare.project_id == project_id)
    )
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    await audit.log_action(db, user, audit.ACTION_SHARE_REVOKE, "project", project_id)
    await db.delete(share)
    return {"status": "revoked"}


@router.get("/shared-with-me", response_model=list[SharedProjectOut])
async def shared_with_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List projects shared with the current user."""
    result = await db.execute(
        select(ProjectShare)
        .where(ProjectShare.user_id == user.id)
        .options(selectinload(ProjectShare.project).selectinload(Project.owner))
    )
    shares = result.scalars().all()
    return [
        {
            "project_id": s.project.id,
            "name": s.project.name,
            "created_at": s.project.created_at.isoformat(),
            "role": s.role,
            "owner_email": s.project.owner.email,
            "owner_name": s.project.owner.full_name,
        }
        for s in shares
    ]
