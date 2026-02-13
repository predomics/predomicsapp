"""Admin endpoints: user management."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import get_admin_user
from ..models.db_models import User, Project, Dataset
from ..models.auth_schemas import AdminUserResponse, AdminUserUpdate

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users with project/dataset counts (admin only)."""
    proj_count = (
        select(Project.user_id, func.count(Project.id).label("project_count"))
        .group_by(Project.user_id)
        .subquery()
    )
    ds_count = (
        select(Dataset.user_id, func.count(Dataset.id).label("dataset_count"))
        .group_by(Dataset.user_id)
        .subquery()
    )

    stmt = (
        select(
            User,
            func.coalesce(proj_count.c.project_count, 0).label("project_count"),
            func.coalesce(ds_count.c.dataset_count, 0).label("dataset_count"),
        )
        .outerjoin(proj_count, User.id == proj_count.c.user_id)
        .outerjoin(ds_count, User.id == ds_count.c.user_id)
        .order_by(User.created_at)
    )
    result = await db.execute(stmt)
    rows = result.all()

    return [
        AdminUserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_admin=user.is_admin,
            created_at=user.created_at,
            project_count=pc,
            dataset_count=dc,
        )
        for user, pc, dc in rows
    ]


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: str,
    body: AdminUserUpdate,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle is_active or is_admin flags for a user (admin only)."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot modify your own admin status")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if body.is_active is not None:
        target.is_active = body.is_active
    if body.is_admin is not None:
        target.is_admin = body.is_admin

    pc = await db.execute(
        select(func.count(Project.id)).where(Project.user_id == user_id)
    )
    dc = await db.execute(
        select(func.count(Dataset.id)).where(Dataset.user_id == user_id)
    )

    return AdminUserResponse(
        id=target.id,
        email=target.email,
        full_name=target.full_name,
        is_active=target.is_active,
        is_admin=target.is_admin,
        created_at=target.created_at,
        project_count=pc.scalar() or 0,
        dataset_count=dc.scalar() or 0,
    )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a user and all their data (admin only). Cascades to projects/datasets."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    await db.delete(target)
    return {"status": "deleted", "email": target.email}
