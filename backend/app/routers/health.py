"""Health check endpoints.

``/health`` is a liveness probe (process is up). ``/health/ready`` is a readiness
probe: it also checks the database and the data volume and returns 503 when
either is unusable.
"""

import shutil
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from ..core.config import settings
from ..core.database import engine
from ..core.version import __version__, ENGINE_REF, ENGINEPY_REF
from ..services.engine import check_engine
from ..services.scitq_client import is_enabled as scitq_is_enabled

router = APIRouter(tags=["health"])

_MIN_FREE_BYTES = 200 * 1024 * 1024


class HealthInfo(BaseModel):
    status: str
    version: str
    gpredomicspy_available: bool
    engine_version: Optional[str] = None
    engine_ref: Optional[str] = None
    enginepy_ref: Optional[str] = None
    scitq_enabled: bool = False


class ReadinessInfo(HealthInfo):
    database: str = "ok"
    storage: str = "ok"


def _engine_version() -> Optional[str]:
    try:
        import gpredomicspy

        return getattr(gpredomicspy, "__version__", None)
    except Exception:
        return None


def _health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "gpredomicspy_available": check_engine(),
        "engine_version": _engine_version(),
        "engine_ref": ENGINE_REF or None,
        "enginepy_ref": ENGINEPY_REF or None,
        "scitq_enabled": scitq_is_enabled(),
    }


@router.get("/health", response_model=HealthInfo)
async def health_check():
    """Liveness: API process is up; reports app and engine versions."""
    return _health()


@router.get("/health/ready", response_model=ReadinessInfo)
async def readiness_check():
    """Readiness: database reachable and data volume writable with free space."""
    info = {**_health(), "database": "ok", "storage": "ok"}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        info["database"] = "unreachable"
    try:
        if shutil.disk_usage(settings.data_dir).free < _MIN_FREE_BYTES:
            info["storage"] = "low disk space"
    except OSError:
        info["storage"] = "unavailable"
    if info["database"] != "ok" or info["storage"] != "ok":
        info["status"] = "degraded"
        return JSONResponse(status_code=503, content=info)
    return info
