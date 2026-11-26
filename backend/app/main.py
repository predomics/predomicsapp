"""PredomicsApp FastAPI application."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .core.config import settings
from .core.version import __version__
from .core import metrics, observability
from .core.database import engine
from .models import db_models  # noqa: F401 — ensure models are registered
from .routers import health, projects, analysis, auth, samples, datasets, sharing, admin, data_explore, export, websocket, templates, webhook_router, predict, dashboard, comments, public, meta_analysis, signature_zoo
from .services.storage import ensure_dirs

# Logging (text or JSON, level from settings) is configured by observability.install().
observability.configure_logging()

_log = logging.getLogger(__name__)


_DEMO_EMAIL = "demo@predomics.com"
_DEMO_PASSWORD = "demo"


async def _run_migrations() -> None:
    """Bring the database schema up to date (Alembic; see ``migrate.py``).

    With PREDOMICS_AUTO_MIGRATE=false the application does not change the schema
    itself: it refuses to start unless the database is already at the current
    revision (run ``python -m backend.app.migrate`` as a separate step).
    """
    from . import migrate

    if migrate.auto_migrate_enabled():
        await migrate.upgrade_database()
    else:
        await migrate.require_up_to_date()


async def _bootstrap_accounts() -> None:
    """Apply the account settings: admin bootstrap and the optional demo user.

    - PREDOMICS_ADMIN_EMAIL: that account (once it exists) is an administrator.
    - PREDOMICS_SEED_DEMO=true: make sure demo@predomics.com / demo exists.
    - Otherwise a leftover demo account that still has the published password is
      deactivated, because anyone could log in with it.
    """
    from .core.security import hash_password, verify_password

    async with engine.begin() as conn:
        admin_email = (settings.admin_email or "").strip().lower()
        if admin_email:
            r = await conn.execute(
                text("UPDATE users SET is_admin = TRUE WHERE lower(email) = :e AND is_admin IS NOT TRUE"),
                {"e": admin_email},
            )
            if r.rowcount:
                _log.info("Granted admin rights to the PREDOMICS_ADMIN_EMAIL account")

        row = (await conn.execute(
            text("SELECT id, hashed_password, is_active FROM users WHERE email = :e"),
            {"e": _DEMO_EMAIL},
        )).first()
        if settings.seed_demo:
            if row is None:
                import uuid
                await conn.execute(text(
                    "INSERT INTO users (id, email, hashed_password, full_name, is_active, is_admin, created_at) "
                    "VALUES (:id, :email, :pw, :name, TRUE, FALSE, CURRENT_TIMESTAMP)"
                ), {"id": uuid.uuid4().hex[:12], "email": _DEMO_EMAIL,
                    "pw": hash_password(_DEMO_PASSWORD), "name": "Demo User"})
                _log.warning("PREDOMICS_SEED_DEMO is on: created %s with a public password", _DEMO_EMAIL)
            elif not row.is_active:
                await conn.execute(text("UPDATE users SET is_active = TRUE WHERE id = :id"), {"id": row.id})
        elif row is not None and row.is_active and verify_password(_DEMO_PASSWORD, row.hashed_password):
            await conn.execute(
                text("UPDATE users SET is_active = FALSE, is_admin = FALSE WHERE id = :id"), {"id": row.id}
            )
            _log.warning(
                "Deactivated %s: it still had the published default password. "
                "Set PREDOMICS_SEED_DEMO=true to keep a public demo account.", _DEMO_EMAIL,
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown events."""
    ensure_dirs()
    # Create or upgrade the schema (Alembic), unless PREDOMICS_AUTO_MIGRATE is off.
    await _run_migrations()
    await _bootstrap_accounts()
    # Recover the jobs of the previous process: queued ones are queued again,
    # interrupted ones are marked failed (see services/jobs.py).
    from .services import jobs as job_runner
    await asyncio.to_thread(job_runner.reconcile_orphaned_jobs)
    # Find out what the installed engine supports and whether the defaults fit it.
    # A few seconds of real (tiny) fits the first time, cached afterwards: do not
    # hold up startup for it.
    from .services import engine as ml_engine

    async def _check_engine() -> None:
        try:
            await asyncio.to_thread(ml_engine.check_startup_compatibility)
        except Exception:  # noqa: BLE001 - diagnostics must never stop the application
            _log.exception("Engine capability check failed")

    engine_check = asyncio.create_task(_check_engine())
    # Periodic clean-up of old job files and backups (a no-op unless retention is configured).
    from .services import retention
    retention.start_scheduler()
    _log.info("PredomicsApp %s started — data_dir=%s", __version__, settings.data_dir)
    yield
    retention.stop_scheduler()
    engine_check.cancel()
    await asyncio.to_thread(job_runner.shutdown)


app = FastAPI(
    title="PredomicsApp API",
    description="Web API for gpredomics — sparse interpretable ML model discovery",
    version=__version__,
    lifespan=lifespan,
    # PREDOMICS_API_DOCS=false hides the interactive documentation and the schema.
    docs_url="/api/docs" if settings.api_docs else None,
    redoc_url="/api/redoc" if settings.api_docs else None,
    openapi_url="/api/openapi.json" if settings.api_docs else None,
)

# Commit the request's database session before its response is sent (see
# database.get_db). Added first so that it is the innermost middleware.
from .core.database import CommitBeforeResponseMiddleware  # noqa: E402
app.add_middleware(CommitBeforeResponseMiddleware)

# CORS for Vue.js dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip compression for large JSON responses
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402
app.add_middleware(GZipMiddleware, minimum_size=1000)



@app.middleware("http")
async def _security_headers(request, call_next):
    """Baseline security headers for every response (also when no reverse proxy adds them)."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


# Request ids, access log, request metrics and error tracking. Added last so that
# it is the outermost middleware and sees every request and response.
observability.install(app)

# Structured error responses
from fastapi.exceptions import RequestValidationError  # noqa: E402
from .core.errors import http_error_handler, generic_error_handler, validation_error_handler  # noqa: E402
app.add_exception_handler(HTTPException, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, generic_error_handler)

# Rate limiting
from .core.rate_limit import limiter  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402
from slowapi import _rate_limit_exceeded_handler  # noqa: E402
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Register routers
# Note: sharing must come before projects so /shared-with-me is matched
# before the /{project_id} catch-all pattern in the projects router.
app.include_router(health.router)
app.include_router(auth.router, prefix="/api")
app.include_router(sharing.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(analysis.router, prefix="/api")
app.include_router(samples.router, prefix="/api")
app.include_router(datasets.router, prefix="/api")
app.include_router(data_explore.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(templates.router, prefix="/api")
app.include_router(webhook_router.router, prefix="/api")
app.include_router(predict.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(comments.router, prefix="/api")
app.include_router(public.router, prefix="/api")
app.include_router(meta_analysis.router, prefix="/api")
app.include_router(signature_zoo.router, prefix="/api")
app.include_router(websocket.router)  # WebSocket (no /api prefix, uses /ws/)

# Prometheus metrics at /metrics (must be registered before the SPA catch-all below).
metrics.install(app)

# Serve Vue.js frontend (production: built into backend/static/)
_static_dir = Path(__file__).parent / "static"
if _static_dir.is_dir():
    from fastapi.responses import FileResponse

    app.mount("/assets", StaticFiles(directory=_static_dir / "assets"), name="assets")

    # Paths that should NOT be handled by the SPA (let FastAPI handle them)
    _reserved_paths = {"health", "api", "ws", "metrics"}
    _static_root = _static_dir.resolve()

    # HEAD as well as GET: uptime monitors commonly probe with HEAD.
    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_spa(full_path: str):
        """Serve Vue.js SPA — all non-API/docs routes return index.html."""
        first_segment = full_path.split("/")[0] if full_path else ""
        if first_segment in _reserved_paths:
            raise HTTPException(status_code=404, detail="Not found")
        # Only ever serve files that really live inside the static directory:
        # "../" (plain or percent-encoded) must not reach the rest of the filesystem.
        try:
            file_path = (_static_dir / full_path).resolve()
        except (OSError, ValueError):
            raise HTTPException(status_code=404, detail="Not found")
        if file_path.is_relative_to(_static_root) and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_static_dir / "index.html")
