"""Shared FastAPI dependencies."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db
from .security import decode_access_token
from ..models.db_models import User, Project, ProjectShare

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate JWT, return the User ORM object."""
    user_id = decode_access_token(credentials.credentials)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


async def get_admin_user(
    user: User = Depends(get_current_user),
) -> User:
    """Require the current user to be an admin."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


async def get_project_with_access(
    project_id: str,
    user: User,
    db: AsyncSession,
    require_role: str = "viewer",
) -> tuple["Project", str]:
    """Return (project, effective_role) or raise 404.

    require_role: "owner" | "editor" | "viewer"
      - "owner"  → only the project owner
      - "editor" → owner or editor share
      - "viewer" → owner, editor, or viewer share
    """
    from sqlalchemy.orm import selectinload
    from ..models.db_models import ProjectDataset, Dataset

    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.dataset_links)
                .selectinload(ProjectDataset.dataset)
                .selectinload(Dataset.files),
            selectinload(Project.jobs),
            selectinload(Project.shares),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Owner always has full access
    if project.user_id == user.id:
        return project, "owner"

    if require_role == "owner":
        raise HTTPException(status_code=404, detail="Project not found")

    # Check shares
    share = next((s for s in project.shares if s.user_id == user.id), None)
    if not share:
        raise HTTPException(status_code=404, detail="Project not found")

    role_rank = {"viewer": 0, "editor": 1, "owner": 2}
    if role_rank.get(share.role, 0) < role_rank.get(require_role, 0):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    return project, share.role
