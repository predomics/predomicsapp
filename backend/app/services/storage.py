"""Filesystem storage — handles file I/O only. Metadata lives in the database."""

from __future__ import annotations
import json
import os
import re
import shutil
import unicodedata
from pathlib import Path

from ..core.config import settings


def ensure_dirs() -> None:
    """Create storage directories if they don't exist."""
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.project_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "backups").mkdir(parents=True, exist_ok=True)


def ensure_project_dirs(project_id: str) -> None:
    """Create project subdirectories on disk."""
    base = settings.project_dir / project_id
    (base / "datasets").mkdir(parents=True, exist_ok=True)
    (base / "jobs").mkdir(parents=True, exist_ok=True)


def save_dataset_file(project_id: str, dataset_id: str, filename: str, content: bytes) -> str:
    """Write dataset bytes into a project's datasets directory, return the file path."""
    if not is_safe_id(project_id) or not is_safe_id(dataset_id):
        raise ValueError("Invalid storage identifier")
    base = settings.project_dir
    dest = _contained(base / project_id / "datasets" / f"{dataset_id}_{safe_filename(filename)}", base)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return str(dest)


def get_dataset_path(project_id: str, dataset_id: str) -> Path | None:
    """Get the file path for a project dataset by prefix match."""
    if not is_safe_id(project_id) or not is_safe_id(dataset_id):
        return None
    datasets_dir = settings.project_dir / project_id / "datasets"
    if not datasets_dir.exists():
        return None
    for f in datasets_dir.iterdir():
        if f.name.startswith(dataset_id):
            return f
    return None


def delete_project_files(project_id: str) -> None:
    """Delete all files for a project from disk."""
    project_path = settings.project_dir / project_id
    if project_path.exists():
        shutil.rmtree(project_path)


def save_job_result(project_id: str, job_id: str, results: dict) -> str:
    """Save job results to disk, return the file path."""
    job_dir = settings.project_dir / project_id / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    result_path = job_dir / "results.json"
    tmp_path = job_dir / "results.json.tmp"
    with open(tmp_path, "w") as f:
        json.dump(results, f, default=str)
    os.replace(tmp_path, result_path)
    return str(result_path)


def get_job_result(project_id: str, job_id: str) -> dict | None:
    """Load job results from disk."""
    result_path = settings.project_dir / project_id / "jobs" / job_id / "results.json"
    if not result_path.exists():
        return None
    with open(result_path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# User-level dataset storage (dataset library)
# ---------------------------------------------------------------------------

def _datasets_base() -> Path:
    """Return the base directory for user-level datasets."""
    return settings.data_dir / "datasets"


_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._ -]+")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def safe_filename(filename: str | None, default: str = "file") -> str:
    """Reduce a client-supplied filename to a harmless single path component.

    Directory parts, control characters and anything outside ``[A-Za-z0-9._ -]``
    are dropped, so the result can never climb out of its directory.
    """
    name = unicodedata.normalize("NFKD", filename or "")
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.replace("\\", "/").split("/")[-1]
    name = _UNSAFE_CHARS.sub("_", name).strip(" .")
    if not name or set(name) <= {"_"}:
        name = default
    if len(name) > 150:
        stem, dot, ext = name.rpartition(".")
        name = (stem[: 150 - len(ext) - 1] + dot + ext) if dot and len(ext) <= 10 else name[:150]
    return name


def is_safe_id(value: str) -> bool:
    """True if ``value`` is a plain identifier usable as a path component."""
    return bool(_ID_RE.match(value or ""))


def _contained(path: Path, base: Path) -> Path:
    """Return ``path`` resolved, or raise if it is not inside ``base``."""
    resolved = path.resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise ValueError(f"Refusing to write outside {base}")
    return resolved


def save_user_dataset_file(user_id: str, dataset_id: str, filename: str, content: bytes) -> str:
    """Write a user-level dataset file to disk, return the file path."""
    if not is_safe_id(user_id) or not is_safe_id(dataset_id):
        raise ValueError("Invalid storage identifier")
    base = _datasets_base()
    dest = _contained(base / user_id / f"{dataset_id}_{safe_filename(filename)}", base)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return str(dest)


def delete_user_dataset_file(disk_path: str) -> None:
    """Delete a single dataset file from disk."""
    p = Path(disk_path)
    if p.exists():
        p.unlink()
