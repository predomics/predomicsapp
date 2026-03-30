"""Application configuration via environment variables."""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "PredomicsApp"
    debug: bool = False

    # Storage paths
    data_dir: Path = Path("data")                     # user workspace (persistent volume)
    upload_dir: Path = Path("data/uploads")
    project_dir: Path = Path("data/projects")
    samples_dir: Path = Path("samples")               # bundled demo datasets (read-only, baked in image)
    sample_dir: Path = Path("samples/qin2014_cirrhosis")  # legacy compat

    # gpredomics defaults
    default_algo: str = "ga"
    default_language: str = "bin,ter,ratio"
    default_data_type: str = "raw,prev"
    default_fit: str = "auc"
    default_population_size: int = 5000
    default_max_epochs: int = 100
    default_thread_number: int = 4

    # Database
    database_url: str = "postgresql+asyncpg://predomics:predomics@localhost:5432/predomics"

    # JWT authentication
    secret_key: str = "CHANGE-ME-IN-PRODUCTION"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours

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

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_auth: str = "10/minute"
    rate_limit_api: str = "100/minute"
    rate_limit_upload: str = "20/minute"
    rate_limit_admin: str = "30/minute"

    model_config = {"env_prefix": "PREDOMICS_"}


settings = Settings()
