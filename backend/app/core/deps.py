"""Shared FastAPI dependencies."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .database import get_db
from .security import decode_token, token_matches_user, verify_password
from ..models.db_models import User, Project, ProjectShare, ApiKey

bearer_scheme = HTTPBearer(auto_error=False)

_API_KEY_PREFIX_LEN = 8
_LAST_USED_GRANULARITY = timedelta(minutes=5)  # avoid a DB write on every API-key request


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    x_api_key: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate JWT or API key, return the User ORM object."""
    # Try JWT first
    if credentials:
        payload = decode_token(credentials.credentials)
        user_id = payload.get("sub") if payload else None
        if user_id:
            result = await db.execute(
                select(User).where(User.id == user_id, User.is_active.is_(True))
            )
            user = result.scalar_one_or_none()
            if user and token_matches_user(payload, user.hashed_password):
                return user

    # Try API key: narrow by the stored prefix, then verify the few candidates.
    # (Scanning and bcrypt-checking every key would let anyone burn CPU with junk headers.)
    if x_api_key and len(x_api_key) >= _API_KEY_PREFIX_LEN:
        result = await db.execute(
            select(ApiKey)
            .where(ApiKey.is_active.is_(True), ApiKey.prefix == x_api_key[:_API_KEY_PREFIX_LEN])
            .options(selectinload(ApiKey.user))
            .limit(5)
        )
        for key in result.scalars().all():
            if await asyncio.to_thread(verify_password, x_api_key, key.key_hash):
                if key.user and key.user.is_active:
                    now = datetime.now(timezone.utc)
                    last = key.last_used_at
                    if last is not None and last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    if last is None or now - last > _LAST_USED_GRANULARITY:
                        key.last_used_at = now
                    return key.user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
    )


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


_ROLE_RANK = {"viewer": 0, "editor": 1, "owner": 2}


async def get_project_access(
    project_id: str,
    user: User,
    db: AsyncSession,
    require_role: str = "viewer",
    *,
    datasets: bool = False,
    jobs: bool = False,
    shares: bool = False,
) -> tuple["Project", str]:
    """Return (project, effective_role) or raise 404/403, loading only what is asked.

    By default this costs one query for the owner (the project row) and two for
    anyone else (plus the caller's own share). Pass ``datasets``, ``jobs`` or
    ``shares`` to eager-load ``project.dataset_links`` (with datasets and files),
    ``project.jobs`` or ``project.shares``; touching a relationship that was not
    requested raises in async SQLAlchemy, so ask for what the handler reads.

    require_role: "owner" | "editor" | "viewer"
      - "owner"  → only the project owner
      - "editor" → owner or editor share
      - "viewer" → owner, editor, or viewer share
    """
    from ..models.db_models import ProjectDataset, Dataset

    options = []
    if datasets:
        options.append(
            selectinload(Project.dataset_links)
            .selectinload(ProjectDataset.dataset)
            .selectinload(Dataset.files)
        )
    if jobs:
        options.append(selectinload(Project.jobs))
    if shares:
        options.append(selectinload(Project.shares))

    stmt = select(Project).where(Project.id == project_id)
    if options:
        stmt = stmt.options(*options)
    project = (await db.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Owner always has full access
    if project.user_id == user.id:
        return project, "owner"

    if require_role == "owner":
        raise HTTPException(status_code=404, detail="Project not found")

    role = (await db.execute(
        select(ProjectShare.role).where(
            ProjectShare.project_id == project_id, ProjectShare.user_id == user.id,
        )
    )).scalars().first()
    if role is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if _ROLE_RANK.get(role, 0) < _ROLE_RANK.get(require_role, 0):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    return project, role


async def get_project_with_access(
    project_id: str,
    user: User,
    db: AsyncSession,
    require_role: str = "viewer",
) -> tuple["Project", str]:
    """Like :func:`get_project_access` but eager-loads datasets, jobs and shares.

    Kept for handlers that read those relationships. Prefer
    :func:`get_project_access` with explicit flags: this variant runs about six
    queries per call.
    """
    return await get_project_access(
        project_id, user, db, require_role, datasets=True, jobs=True, shares=True,
    )
