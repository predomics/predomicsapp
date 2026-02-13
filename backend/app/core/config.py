"""Application configuration via environment variables."""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "PredomicsApp"
    debug: bool = False

    # Storage paths
    data_dir: Path = Path("data")
    upload_dir: Path = Path("data/uploads")
    project_dir: Path = Path("data/projects")
    sample_dir: Path = Path("data/qin2014_cirrhosis")

    # gpredomics defaults
    default_algo: str = "ga"
    default_language: str = "bin,ter,ratio"
    default_data_type: str = "raw,prev"
    default_fit: str = "auc"
    default_population_size: int = 5000
    default_max_epochs: int = 100
    default_thread_number: int = 4

    # CORS (for Vue.js dev server)
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = {"env_prefix": "PREDOMICS_"}


settings = Settings()
