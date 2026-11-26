"""Application configuration via environment variables (prefix ``PREDOMICS_``)."""

import logging
import os
import secrets
from pathlib import Path
from pydantic_settings import BaseSettings

_log = logging.getLogger(__name__)

# Secrets that have shipped in this repo's defaults/compose files and must never be used.
_KNOWN_INSECURE_SECRETS = {
    "",
    "CHANGE-ME-IN-PRODUCTION",
    "change-me-in-production",
    "dev-secret-key",
}


class Settings(BaseSettings):
    app_name: str = "PredomicsApp"
    debug: bool = False

    # Storage paths
    data_dir: Path = Path("data")                     # user workspace (persistent volume)
    upload_dir: Path | None = None     # default: <data_dir>/uploads
    project_dir: Path | None = None    # default: <data_dir>/projects
    samples_dir: Path = Path("samples")               # bundled demo datasets (read-only, baked in image)

    # Database
    database_url: str = "postgresql+asyncpg://predomics:predomics@localhost:5432/predomics"

    # JWT authentication
    secret_key: str = "CHANGE-ME-IN-PRODUCTION"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480   # 8 hours; clients extend a live session with /auth/refresh

    # Accounts
    registration_enabled: bool = True   # False = only admins can create accounts
    admin_email: str = ""               # this account is granted admin rights (bootstrap)
    seed_demo: bool = False             # True = create demo@predomics.com / demo at startup
    password_min_length: int = 8
    require_email_verification: bool = False   # True = new accounts must confirm their email (needs SMTP)
    login_throttle_enabled: bool = True        # back-off after repeated failed logins (per account and per IP)
    login_throttle_free_attempts: int = 5      # failures allowed before the back-off starts
    login_throttle_max_minutes: int = 15       # longest wait between attempts

    # Uploads and jobs
    max_upload_mb: int = 500            # per-file upload limit
    max_concurrent_jobs: int = 2        # analysis jobs running at the same time (others queue)
    job_timeout_minutes: int = 0        # 0 = no timeout
    max_jobs_per_user: int = 0          # jobs one user may run at once (0 = no per-user limit)
    requeue_interrupted: bool = False   # True = re-run jobs that were running when the server stopped
    auto_migrate: bool = True           # False = never change the schema at startup; run the migrate command instead
    ga_parent_guard: bool = True        # reject GA settings that would select fewer than two parents (engine panic)
    max_threads_per_job: int = 0        # 0 = number of CPUs
    user_quota_mb: int = 0              # per-user storage (datasets + job results); 0 = unlimited
    job_retention_days: int = 0         # delete finished jobs older than this; 0 = keep forever
    backup_retention_count: int = 0     # keep only the newest N in-app backups; 0 = keep all
    webhook_allow_private: bool = False  # True = webhooks may target private/intranet addresses
    allow_mock_engine: bool = False     # True = fake results when gpredomicspy is missing (tests/dev only)

    # CORS (for Vue.js dev server)
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # SMTP (optional — password reset works without email configured)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_tls: bool = True
    frontend_url: str = "http://localhost:5173"

    # scitq distributed task queue (optional — empty = disabled, local execution)
    scitq_server: str = ""        # e.g. "scitq-server:5000"
    scitq_token: str = ""         # auth token (for future scitq versions)
    scitq_container: str = ""     # Docker image for workers (e.g. "predomics-app:latest")

    # Observability
    log_format: str = "text"            # "text" or "json" (one JSON object per line, with request ids)
    log_level: str = "INFO"
    metrics_token: str = ""             # bearer token for GET /metrics; empty = endpoint disabled
    sentry_dsn: str = ""                # error tracking, used only if the sentry-sdk package is installed
    api_docs: bool = True               # False = do not serve /api/docs, /api/redoc, /api/openapi.json

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_api: str = "100/minute"   # default per-user limit; login/reset/upload have fixed stricter limits

    model_config = {"env_prefix": "PREDOMICS_"}


def _resolve_secret_key(s: Settings) -> str:
    """Return a usable JWT secret.

    A known default (or empty) secret lets anyone forge tokens, so outside debug
    mode it is replaced by a random one persisted in ``<data_dir>/.secret_key``.
    """
    if s.secret_key not in _KNOWN_INSECURE_SECRETS:
        if len(s.secret_key) < 32 and not s.debug:
            _log.warning("PREDOMICS_SECRET_KEY is shorter than 32 characters; use a longer random value.")
        return s.secret_key
    if s.debug:
        return s.secret_key or "dev-secret-key"
    key_file = Path(s.data_dir) / ".secret_key"
    try:
        if key_file.exists():
            key = key_file.read_text().strip()
            if len(key) >= 32:
                return key
        key = secrets.token_urlsafe(48)
        key_file.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(key_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(key)
        _log.warning(
            "PREDOMICS_SECRET_KEY is unset or a known default; generated a random key in %s. "
            "Set PREDOMICS_SECRET_KEY explicitly to control it.", key_file,
        )
        return key
    except OSError as exc:  # read-only data dir: fall back to a per-process key
        _log.warning("Could not persist a generated secret key (%s); sessions will reset on restart.", exc)
        return secrets.token_urlsafe(48)


def validate_settings(s: Settings) -> None:
    """Fail fast on combinations that cannot work."""
    if s.log_format not in ("text", "json"):
        raise RuntimeError("PREDOMICS_LOG_FORMAT must be 'text' or 'json'")
    if s.require_email_verification and not s.debug and not (s.smtp_host and s.smtp_from):
        raise RuntimeError(
            "PREDOMICS_REQUIRE_EMAIL_VERIFICATION is on but SMTP is not configured "
            "(PREDOMICS_SMTP_HOST and PREDOMICS_SMTP_FROM): nobody could ever verify an account."
        )


settings = Settings()
validate_settings(settings)
# Storage sub-directories follow data_dir unless set explicitly.
if settings.upload_dir is None:
    settings.upload_dir = Path(settings.data_dir) / "uploads"
if settings.project_dir is None:
    settings.project_dir = Path(settings.data_dir) / "projects"
settings.secret_key = _resolve_secret_key(settings)
