"""Backup and restore service — full system export/import as portable archives.

A backup is a ``.tar.gz`` holding

* ``database/<table>.json`` — one file per table, for **every** table of the
  schema (taken from ``Base.metadata``, so new tables are covered automatically);
* ``datasets/`` — the dataset library files;
* ``projects/`` — job directories (results, logs, parameters);
* ``stores/*.json`` — file-based settings (admin defaults, signature zoo,
  templates, scitq configuration);
* ``manifest.json``.

Restoring in ``replace`` mode makes the instance equal to the backup. It is
ordered so that a failure leaves the instance as it was: the archive is
unpacked and validated, the new files are staged next to their destination, the
database is rewritten in one transaction, and only after the commit are the
staged files swapped in. Tables an (older) archive does not contain are kept
rather than wiped.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tarfile
import tempfile
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import DateTime, delete, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.database import Base
from ..models import db_models  # noqa: F401 - registers every table on Base.metadata

_log = logging.getLogger(__name__)

BACKUP_DIR = Path(settings.data_dir) / "backups"

# File-based stores kept in the data directory.
JSON_STORES = ("admin_defaults.json", "signature_zoo.json", "templates.json", "scitq_config.json")

# Columns that hold absolute paths (rewritten when restoring into another data dir).
_PATH_COLUMNS = {"dataset_files": ("disk_path",), "jobs": ("results_path",)}


def _tables():
    """All tables, parents before children."""
    return list(Base.metadata.sorted_tables)


# Kept for callers that introspect the export order: (table name, Table).
TABLE_EXPORT_ORDER = [(t.name, t) for t in _tables()]


def ensure_backup_dir() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR


def _jsonable(val):
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    return val


def _serialize_row(obj) -> dict:
    """Convert an ORM object or a result row to a JSON-serializable dict."""
    if hasattr(obj, "_mapping"):
        return {k: _jsonable(v) for k, v in obj._mapping.items()}
    return {col.name: _jsonable(getattr(obj, col.name)) for col in obj.__table__.columns}


def _manifest_sidecar(archive: Path) -> Path:
    return archive.with_name(archive.name + ".manifest.json")


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def _write_archive(archive_path: Path, tables: dict[str, list[dict]], manifest: dict) -> None:
    """Blocking part of a backup: write the tar.gz (streams the data directories)."""
    data_dir = Path(settings.data_dir)
    tmp_archive = archive_path.with_name(archive_path.name + ".partial")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        db_dir = tmp / "database"
        db_dir.mkdir()
        for name, records in tables.items():
            (db_dir / f"{name}.json").write_text(json.dumps(records, default=str))
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2))

        try:
            with tarfile.open(tmp_archive, "w:gz") as tar:
                tar.add(str(tmp / "manifest.json"), arcname="backup/manifest.json")
                tar.add(str(db_dir), arcname="backup/database")
                datasets_src = data_dir / "datasets"
                if datasets_src.is_dir():
                    tar.add(str(datasets_src), arcname="backup/datasets")
                if Path(settings.project_dir).is_dir():
                    tar.add(str(settings.project_dir), arcname="backup/projects")
                for store in JSON_STORES:
                    src = data_dir / store
                    if src.is_file():
                        tar.add(str(src), arcname=f"backup/stores/{store}")
            tmp_archive.replace(archive_path)
        except BaseException:
            tmp_archive.unlink(missing_ok=True)
            raise
    try:
        _manifest_sidecar(archive_path).write_text(json.dumps(manifest, indent=2))
    except OSError:
        pass


async def create_backup(db: AsyncSession, description: str = "") -> dict:
    """Create a full system backup archive.

    Returns metadata dict with backup_id, filename, size, table_counts.
    """
    ensure_backup_dir()
    backup_id = uuid.uuid4().hex[:12]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_name = f"predomics_backup_{timestamp}_{backup_id}.tar.gz"
    archive_path = BACKUP_DIR / archive_name

    # 1. Read every table (async DB work stays on the event loop)
    tables: dict[str, list[dict]] = {}
    for table in _tables():
        rows = (await db.execute(select(table))).all()
        tables[table.name] = [_serialize_row(r) for r in rows]
    table_counts = {name: len(rows) for name, rows in tables.items()}

    manifest = {
        "backup_id": backup_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "description": description,
        "format": 2,
        "tables": list(tables.keys()),
        "table_counts": table_counts,
        "data_dir": str(Path(settings.data_dir).resolve()),
        "project_dir": str(Path(settings.project_dir).resolve()),
    }

    # 2. Files and compression in a worker thread
    await asyncio.to_thread(_write_archive, archive_path, tables, manifest)

    size_bytes = archive_path.stat().st_size
    _log.info("Backup %s created: %s (%.1f MB)", backup_id, archive_name, size_bytes / 1e6)

    return {
        "backup_id": backup_id,
        "filename": archive_name,
        "size_bytes": size_bytes,
        "created_at": manifest["created_at"],
        "description": description,
        "table_counts": table_counts,
    }


def list_backups() -> list[dict]:
    """List all available backup archives with their manifests."""
    ensure_backup_dir()
    backups = []
    for f in sorted(BACKUP_DIR.glob("predomics_backup_*.tar.gz"), reverse=True):
        try:
            sidecar = _manifest_sidecar(f)
            if sidecar.exists():
                manifest = json.loads(sidecar.read_text())
            else:  # archives made before sidecars existed: read it once, then remember
                with tarfile.open(f, "r:gz") as tar:
                    manifest = json.loads(tar.extractfile("backup/manifest.json").read())
                try:
                    sidecar.write_text(json.dumps(manifest, indent=2))
                except OSError:
                    pass
            manifest["filename"] = f.name
            manifest["size_bytes"] = f.stat().st_size
            backups.append(manifest)
        except Exception as e:  # noqa: BLE001
            backups.append({
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "error": str(e),
            })
    return backups


def get_backup_path(backup_id: str) -> Optional[Path]:
    """Find the archive file for a given backup_id."""
    if not backup_id or not backup_id.isalnum():
        return None
    ensure_backup_dir()
    for f in BACKUP_DIR.glob(f"predomics_backup_*_{backup_id}.tar.gz"):
        return f
    return None


def delete_backup(backup_id: str) -> bool:
    """Delete a backup archive. Returns True if found and deleted."""
    path = get_backup_path(backup_id)
    if path and path.exists():
        path.unlink()
        _manifest_sidecar(path).unlink(missing_ok=True)
        return True
    return False


async def save_upload(upload, suffix: str = ".tar.gz", max_mb: int | None = None) -> Path:
    """Stream an uploaded archive to a temporary file (never whole in memory).

    Returns the temp path; the caller deletes it. Raises ValueError if the
    upload exceeds ``max_mb`` megabytes.
    """
    limit = max_mb * 1024 * 1024 if max_mb else None
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    path = Path(tmp.name)
    total = 0
    try:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if limit is not None and total > limit:
                raise ValueError(f"Archive is too large (limit {max_mb} MB)")
            await asyncio.to_thread(tmp.write, chunk)
    except BaseException:
        tmp.close()
        path.unlink(missing_ok=True)
        raise
    tmp.close()
    return path


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

def _extract(archive_path: Path, dest: Path) -> tuple[Path, dict]:
    """Unpack and validate an archive (blocking). Returns (backup root, manifest)."""
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(dest, filter="data")
    root = dest / "backup"
    if not root.is_dir():
        raise ValueError("Invalid backup archive: missing 'backup/' root")
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise ValueError("Invalid backup archive: missing manifest.json")
    if not (root / "database").is_dir():
        raise ValueError("Invalid backup archive: missing database/ directory")
    try:
        manifest = json.loads(manifest_path.read_text())
    except ValueError:
        raise ValueError("Invalid backup archive: unreadable manifest.json")
    return root, manifest


def _load_table_records(db_dir: Path, name: str) -> list[dict] | None:
    f = db_dir / f"{name}.json"
    if not f.exists():
        return None
    data = json.loads(f.read_text())
    if not isinstance(data, list):
        raise ValueError(f"Invalid backup archive: database/{name}.json is not a list")
    return data


def _coerce(table, record: dict, path_map: list[tuple[str, str]]) -> dict:
    """Keep known columns, parse datetimes, remap absolute paths."""
    out = {}
    for col in table.columns:
        if col.name not in record:
            continue
        val = record[col.name]
        if val is not None and isinstance(col.type, DateTime):
            try:
                val = datetime.fromisoformat(str(val))
            except (ValueError, TypeError):
                pass
        if val is not None and col.name in _PATH_COLUMNS.get(table.name, ()):
            for old, new in path_map:
                if isinstance(val, str) and old and val.startswith(old):
                    val = new + val[len(old):]
                    break
        out[col.name] = val
    return out


def _stage_files(root: Path, stage: Path) -> dict[str, Path]:
    """Copy the archive's files next to their destination (blocking). No live file is touched."""
    staged: dict[str, Path] = {}
    data_dir = Path(settings.data_dir)
    if (root / "datasets").is_dir():
        staged[str(data_dir / "datasets")] = stage / "datasets"
        shutil.copytree(root / "datasets", stage / "datasets")
    if (root / "projects").is_dir():
        staged[str(Path(settings.project_dir))] = stage / "projects"
        shutil.copytree(root / "projects", stage / "projects")
    stores = root / "stores"
    for store in JSON_STORES:
        src = stores / store
        if not src.is_file() and store == "admin_defaults.json":
            src = root / store  # format 1 kept it at the top level
        if src.is_file():
            (stage / "stores").mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, stage / "stores" / store)
            staged[str(data_dir / store)] = stage / "stores" / store
    return staged


def _swap_files(staged: dict[str, Path], mode: str, stage: Path) -> None:
    """Put staged files in place (blocking). Called only after the DB commit."""
    for dest_str, src in staged.items():
        dest = Path(dest_str)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            if mode == "replace":
                old = None
                if dest.exists():
                    old = dest.with_name(f".{dest.name}.old-{stage.name}")
                    dest.rename(old)
                try:
                    src.rename(dest)
                except OSError:  # different filesystem
                    shutil.copytree(src, dest)
                if old is not None:
                    shutil.rmtree(old, ignore_errors=True)
            else:
                shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            if mode == "replace" or not dest.exists():
                shutil.copy2(src, dest)
    shutil.rmtree(stage, ignore_errors=True)


async def restore_backup(
    archive_path: Path,
    db: AsyncSession,
    mode: str = "replace",
) -> dict:
    """Restore from a backup archive.

    mode="replace": make the instance equal to the backup.
    mode="merge":   insert records that don't conflict (skip on PK collision).

    Returns summary dict with counts of restored records.
    """
    if mode not in ("replace", "merge"):
        raise ValueError("mode must be 'replace' or 'merge'")

    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".restore-", dir=str(data_dir)))
    staged: dict[str, Path] = {}
    restored_counts: dict[str, int] = {}
    preserved_counts: dict[str, int] = {}

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            root, manifest = await asyncio.to_thread(_extract, archive_path, Path(tmpdir))
            db_dir = root / "database"

            # Absolute paths recorded by another installation are rewritten to this one.
            path_map: list[tuple[str, str]] = []
            for key, here in (("project_dir", settings.project_dir), ("data_dir", settings.data_dir)):
                old = manifest.get(key)
                new = str(Path(here).resolve())
                if old and old != new:
                    path_map.append((old, new))

            tables = _tables()
            records: dict[str, list[dict] | None] = {}
            for table in tables:
                records[table.name] = await asyncio.to_thread(_load_table_records, db_dir, table.name)

            # Stage the files first: a bad archive or a full disk fails here,
            # before anything live has changed.
            staged = await asyncio.to_thread(_stage_files, root, stage)

        try:
            keep: dict[str, list[dict]] = {}
            if mode == "replace":
                # Tables the archive does not contain (older backups) are kept:
                # remember their rows, because deleting their parents cascades.
                for table in tables:
                    if records[table.name] is None:
                        rows = (await db.execute(select(table))).all()
                        keep[table.name] = [dict(r._mapping) for r in rows]
                for table in reversed(tables):
                    await db.execute(delete(table))
                await db.flush()

            for table in tables:
                recs = records[table.name]
                if recs is None:
                    restored_counts[table.name] = 0
                    continue
                pk_cols = [c.name for c in table.primary_key.columns]
                count = 0
                for record in recs:
                    row = _coerce(table, record, path_map)
                    if mode == "merge" and pk_cols and all(k in row for k in pk_cols):
                        cond = [table.c[k] == row[k] for k in pk_cols]
                        exists = (await db.execute(select(table.c[pk_cols[0]]).where(*cond))).first()
                        if exists:
                            continue
                    if mode == "merge":
                        try:
                            async with db.begin_nested():
                                await db.execute(insert(table).values(**row))
                        except IntegrityError:
                            continue  # unique conflict (e.g. same e-mail under another id)
                    else:
                        await db.execute(insert(table).values(**row))
                    count += 1
                await db.flush()
                restored_counts[table.name] = count

            # Re-insert kept rows whose parents still exist.
            for table in tables:
                rows = keep.get(table.name)
                if not rows:
                    continue
                n = 0
                for row in rows:
                    try:
                        async with db.begin_nested():
                            await db.execute(insert(table).values(**row))
                        n += 1
                    except IntegrityError:
                        continue
                preserved_counts[table.name] = n

            await db.commit()
        except BaseException:
            await db.rollback()
            raise

        # The database now describes the backup: put the files in place.
        await asyncio.to_thread(_swap_files, staged, mode, stage)
    except BaseException:
        await asyncio.to_thread(shutil.rmtree, stage, True)
        raise

    _log.info("Backup restored (%s mode): %s", mode, restored_counts)
    return {
        "status": "restored",
        "mode": mode,
        "manifest": manifest,
        "restored_counts": restored_counts,
        "preserved_counts": preserved_counts,
    }
