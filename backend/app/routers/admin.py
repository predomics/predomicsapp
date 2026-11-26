"""Admin endpoints: user management, default configuration, backup/restore, audit log."""

import asyncio
import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.config import settings
from ..core.database import get_db
from ..core.deps import get_admin_user, get_current_user
from ..core.rate_limit import limiter
from ..core.security import hash_password
from ..models.db_models import User, Project, Dataset, AuditLog
from ..models.auth_schemas import AdminUserResponse, AdminUserUpdate
from ..models.api_schemas import (
    UserActionResult, BackupInfo, BackupDeleted, RestoreResult, AuditLogPage, ScitqView,
    ScitqTestResult, RetentionReport,
)
from ..services import audit
from ..services import scitq_client
from ..services import lockout, quota, retention

DEFAULTS_PATH = Path(settings.data_dir) / "admin_defaults.json"

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    include_usage: bool = True,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users with project/dataset counts and storage used (admin only).

    ``include_usage=false`` skips the storage walk on installations with many users.
    """
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

    usage: dict[str, int] = {}
    if include_usage:
        owned = await db.execute(select(Project.user_id, Project.id))
        projects_by_user: dict[str, list[str]] = {}
        for uid, pid in owned.all():
            projects_by_user.setdefault(uid, []).append(pid)

        def _all_usage() -> dict[str, int]:
            return {u.id: quota._usage(u.id, projects_by_user.get(u.id, [])) for u, _pc, _dc in rows}

        usage = await asyncio.to_thread(_all_usage)

    return [
        AdminUserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_admin=user.is_admin,
            created_at=user.created_at,
            email_verified=user.email_verified,
            project_count=pc,
            dataset_count=dc,
            used_bytes=usage.get(user.id),
        )
        for user, pc, dc in rows
    ]


class AdminUserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str
    full_name: str = Field("", max_length=200)
    is_admin: bool = False


@router.post("/users", response_model=AdminUserResponse, status_code=201)
async def create_user(
    body: AdminUserCreate,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Create an account (admin only).

    This is how accounts are made when PREDOMICS_REGISTRATION_ENABLED is false.
    The address counts as verified: an administrator vouches for it.
    """
    email = body.email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    if len(body.password or "") < settings.password_min_length:
        raise HTTPException(
            status_code=422,
            detail=f"Password must be at least {settings.password_min_length} characters long",
        )
    taken = await db.execute(select(User.id).where(func.lower(User.email) == email))
    if taken.first():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name.strip(),
        is_admin=body.is_admin,
        email_verified=True,
    )
    db.add(user)
    await db.flush()
    await audit.log_action(db, admin, audit.ACTION_ADMIN_USER_UPDATE, "user", user.id,
                           details={"created": email, "is_admin": body.is_admin})
    return AdminUserResponse(
        id=user.id, email=user.email, full_name=user.full_name, is_active=user.is_active,
        is_admin=user.is_admin, created_at=user.created_at, email_verified=True,
    )


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: str,
    body: AdminUserUpdate,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle is_active, is_admin or email_verified for a user (admin only)."""
    if user_id == admin.id and (body.is_active is not None or body.is_admin is not None):
        raise HTTPException(status_code=400, detail="Cannot modify your own admin status")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if body.is_active is not None:
        target.is_active = body.is_active
    if body.is_admin is not None:
        target.is_admin = body.is_admin
    if body.email_verified is not None:
        target.email_verified = body.email_verified
        if body.email_verified:
            target.email_verify_token_hash = None
            target.email_verify_expires_at = None

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
        email_verified=target.email_verified,
        project_count=pc.scalar() or 0,
        dataset_count=dc.scalar() or 0,
    )


@router.delete("/users/{user_id}", response_model=UserActionResult)
async def delete_user(
    request: Request,
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

    await audit.log_action(db, admin, audit.ACTION_ADMIN_USER_DELETE, "user", user_id, details={"email": target.email}, ip_address=request.client.host if hasattr(request, 'client') else None)
    await db.delete(target)
    return {"status": "deleted", "email": target.email}


def _load_defaults() -> dict:
    """Load admin defaults from disk."""
    if DEFAULTS_PATH.exists():
        return json.loads(DEFAULTS_PATH.read_text())
    return {}


def _save_defaults(data: dict) -> None:
    """Save admin defaults to disk."""
    DEFAULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULTS_PATH.write_text(json.dumps(data, indent=2))


@router.get("/defaults", response_model=dict[str, Any])
async def get_defaults(admin: User = Depends(get_admin_user)):
    """Get the admin default parameter overrides (admin only)."""
    return _load_defaults()


@router.get("/defaults/public", response_model=dict[str, Any])
async def get_defaults_public(user: User = Depends(get_current_user)):
    """Get the admin default parameter overrides (any signed-in user).

    Used by the Parameters form to show current server defaults.
    """
    return _load_defaults()


_DEFAULT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*$")


@router.put("/defaults", response_model=dict[str, Any])
async def set_defaults(body: dict = Body(...), admin: User = Depends(get_admin_user)):
    """Set admin default parameter overrides (admin only).

    Accepts a flat dict of section.key overrides, e.g.:
    {"general.language": "bin,ter", "ga.population_size": 3000, "voting.vote": true}
    Keys must look like ``section.key`` and values must be scalars.
    """
    bad = [k for k, v in body.items()
           if not isinstance(k, str) or not _DEFAULT_KEY_RE.match(k)
           or not (v is None or isinstance(v, (str, int, float, bool)))]
    if bad or len(body) > 500:
        raise HTTPException(
            status_code=422,
            detail="Defaults must be a flat object of 'section.key': scalar. Invalid: " + ", ".join(map(str, bad[:5])),
        )
    _save_defaults(body)
    return body


# ---------------------------------------------------------------------------
# Backup & Restore
# ---------------------------------------------------------------------------

from ..services import backup as backup_service  # noqa: E402


@router.post("/backup", response_model=BackupInfo, response_model_exclude_unset=True)
async def create_backup(
    description: str = "",
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a full system backup (admin only). Returns backup metadata."""
    try:
        result = await backup_service.create_backup(db, description)
        return result
    except Exception:
        _log.exception("Backup failed")
        raise HTTPException(status_code=500, detail="Backup failed. See the server log for details.")


@router.get("/backup/list", response_model=list[BackupInfo], response_model_exclude_unset=True)
async def list_backups(admin: User = Depends(get_admin_user)):
    """List all available backups (admin only)."""
    return await asyncio.to_thread(backup_service.list_backups)


@router.get("/backup/download/{backup_id}", response_class=FileResponse,
            responses={200: {"content": {"application/gzip": {}}, "description": "The backup archive"}})
async def download_backup(
    backup_id: str,
    admin: User = Depends(get_admin_user),
):
    """Download a backup archive (admin only)."""
    path = backup_service.get_backup_path(backup_id)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    return FileResponse(
        path,
        media_type="application/gzip",
        filename=path.name,
    )


@router.delete("/backup/{backup_id}", response_model=BackupDeleted)
async def delete_backup_endpoint(
    backup_id: str,
    admin: User = Depends(get_admin_user),
):
    """Delete a backup archive (admin only)."""
    if not backup_service.delete_backup(backup_id):
        raise HTTPException(status_code=404, detail="Backup not found")
    return {"status": "deleted", "backup_id": backup_id}


@router.post("/restore", response_model=RestoreResult, response_model_exclude_unset=True)
async def restore_backup(
    file: UploadFile = File(...),
    mode: str = Query("replace", pattern="^(replace|merge)$"),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload and restore from a backup archive (admin only).

    mode: "replace" (wipe and replace) or "merge" (skip conflicts).
    """
    if not (file.filename or "").endswith((".tar.gz", ".tgz")):
        raise HTTPException(status_code=400, detail="Expected a .tar.gz archive")

    # Stream to disk: archives can be far larger than available memory.
    with tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz") as tmp:
        while chunk := await file.read(1024 * 1024):
            tmp.write(chunk)
        tmp_path = Path(tmp.name)

    try:
        result = await backup_service.restore_backup(tmp_path, db, mode=mode)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        _log.exception("Restore failed")
        raise HTTPException(status_code=500, detail="Restore failed. See the server log for details.")
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------


@router.get("/audit-log", response_model=AuditLogPage)
async def get_audit_log(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    user_id: str = None,
    action: str = None,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Query audit log with pagination and filters (admin only)."""
    query = select(AuditLog).order_by(AuditLog.created_at.desc())
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if action:
        query = query.where(AuditLog.action == action)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query.options(selectinload(AuditLog.user)))
    entries = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "entries": [
            {
                "id": e.id,
                "user_email": e.user.email if e.user else None,
                "user_name": e.user.full_name if e.user else None,
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "details": e.details,
                "ip_address": e.ip_address,
                "created_at": e.created_at.isoformat(),
            }
            for e in entries
        ],
    }


# ---------------------------------------------------------------------------
# Admin Password Reset
# ---------------------------------------------------------------------------


@router.post("/users/{user_id}/reset-password", response_model=UserActionResult)
async def admin_reset_password(
    user_id: str,
    new_password: str = Body(..., embed=True),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin can reset any user's password directly."""
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if len(new_password or "") < settings.password_min_length:
        raise HTTPException(
            status_code=422,
            detail=f"Password must be at least {settings.password_min_length} characters long",
        )
    target.hashed_password = hash_password(new_password)
    lockout.unlock_account(target.email)   # the person can sign in straight away
    return {"status": "password_reset", "email": target.email}


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


@router.post("/retention/run", response_model=RetentionReport)
async def run_retention(
    dry_run: bool = Query(True, description="true = only report what would be deleted"),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply the retention rules now, or preview them (admin only).

    Rules come from PREDOMICS_JOB_RETENTION_DAYS and PREDOMICS_BACKUP_RETENTION_COUNT;
    a rule set to 0 deletes nothing. The default is a dry run.
    """
    report = await asyncio.to_thread(retention.run_retention, dry_run)
    if not dry_run and (report["jobs"] or report["backups"]):
        await audit.log_action(db, admin, "admin.retention.run", details={
            "jobs": len(report["jobs"]), "backups": len(report["backups"]),
            "bytes_freed": report["bytes_freed"],
        })
    return report


# ---------------------------------------------------------------------------
# scitq Distributed Task Queue Configuration
# ---------------------------------------------------------------------------


def _scitq_view(cfg: dict) -> dict:
    """scitq settings for the admin UI. The token itself never leaves the server."""
    return {
        "server": cfg["server"],
        "token": "",
        "token_set": bool(cfg["token"]),
        "container": cfg["container"],
        "enabled": scitq_client.is_enabled(),
        "package_installed": scitq_client._HAS_SCITQ,
    }


class ScitqConfigUpdate(BaseModel):
    """scitq settings. Leave ``token`` empty to keep the stored one; set ``clear_token`` to remove it."""
    server: str = Field("", max_length=255)
    token: str = Field("", max_length=1000)
    container: str = Field("", max_length=255)
    clear_token: bool = False


@router.get("/scitq", response_model=ScitqView)
async def get_scitq_config(admin: User = Depends(get_admin_user)):
    """Get current scitq configuration and status (admin only)."""
    cfg = scitq_client.get_config()
    return _scitq_view(cfg)


@router.put("/scitq", response_model=ScitqView)
async def set_scitq_config(
    body: ScitqConfigUpdate,
    admin: User = Depends(get_admin_user),
):
    """Update scitq configuration (admin only)."""
    current = scitq_client.get_config()
    token = "" if body.clear_token else (body.token or current["token"])
    scitq_client.save_runtime_config({
        "server": body.server.strip(),
        "token": token,
        "container": body.container.strip(),
    })
    cfg = scitq_client.get_config()
    return _scitq_view(cfg)


@router.post("/scitq/test", response_model=ScitqTestResult, response_model_exclude_unset=True)
async def test_scitq_connection(admin: User = Depends(get_admin_user)):
    """Test connectivity to the configured scitq server (admin only)."""
    return await asyncio.to_thread(scitq_client.test_connection)
