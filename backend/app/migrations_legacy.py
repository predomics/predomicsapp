"""Pre-Alembic schema migrations (v2 … v24), kept for upgrading old databases.

Until November 2026 the application migrated its schema with the hand-written
functions below, run at every startup and recorded in ``schema_versions``.
Schema changes are now Alembic revisions (``backend/alembic``). These functions
are frozen: they run exactly once, for a database that predates Alembic, to
bring it to the "v24" state that the Alembic baseline revision represents.
``backend/app/migrate.py`` decides when that is needed.

Do not add migrations here. New schema changes are Alembic revisions.

The function bodies are unchanged from ``main.py``. Many of them wrap a
statement in ``try/except: pass``; on PostgreSQL a failed statement aborts the
whole transaction, which used to make every later statement fail too. They are
therefore run through :class:`SavepointConnection`, which isolates each
statement in a savepoint (a failure rolls back only that statement) and logs it.
"""

from __future__ import annotations

import logging
import secrets
import shutil
from pathlib import Path

from sqlalchemy import text

from .core.config import settings

_log = logging.getLogger(__name__)


def _infer_role(filename):
    # Imported lazily: routers must not be loaded just to import this module.
    from .routers.datasets import _infer_role as infer

    return infer(filename)


class SavepointConnection:
    """Wraps an AsyncConnection so every statement runs in its own savepoint.

    A statement that fails is rolled back alone and the error is logged with the
    statement, then re-raised for the caller's own handling; the surrounding
    transaction stays usable.
    """

    def __init__(self, conn):
        self._conn = conn

    @property
    def dialect(self):
        return self._conn.dialect

    async def execute(self, statement, *args, **kwargs):
        try:
            async with self._conn.begin_nested():
                return await self._conn.execute(statement, *args, **kwargs)
        except Exception as exc:
            first_line = " ".join(str(statement).split())[:160]
            _log.warning("Legacy migration statement failed (%s): %s", type(exc).__name__, first_line)
            raise

    async def run_sync(self, fn, *args, **kwargs):
        return await self._conn.run_sync(fn, *args, **kwargs)


async def _migrate_datasets_to_user_library(conn):
    """Migrate datasets from project-level to user-level storage.

    Adds user_id/description columns to datasets, populates them from
    project ownership, creates project_datasets junction entries, and
    copies files to user-level storage. Idempotent.
    """
    # Check if migration already applied
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v2_dataset_library'")
        )
        if r.scalar():
            return
    except Exception:
        pass

    # Add user_id column if missing
    r = await conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'datasets' AND column_name = 'user_id'"
    ))
    if not r.scalar():
        _log.info("Migration: adding user_id and description columns to datasets")
        await conn.execute(text("ALTER TABLE datasets ADD COLUMN user_id VARCHAR(12)"))
        await conn.execute(text("ALTER TABLE datasets ADD COLUMN description TEXT DEFAULT ''"))

    # Check if old project_id column exists (needs migration)
    r = await conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'datasets' AND column_name = 'project_id'"
    ))
    if not r.scalar():
        # No project_id column — fresh install, nothing to migrate
        try:
            await conn.execute(text(
                "INSERT INTO schema_versions (version, applied_at) "
                "VALUES ('v2_dataset_library', NOW()) ON CONFLICT DO NOTHING"
            ))
        except Exception:
            pass
        return

    # Migrate datasets: set user_id, create junction entries, copy files
    rows = await conn.execute(text(
        "SELECT d.id, d.filename, d.disk_path, d.project_id, p.user_id "
        "FROM datasets d JOIN projects p ON d.project_id = p.id "
        "WHERE d.user_id IS NULL"
    ))
    to_migrate = rows.fetchall()

    if to_migrate:
        _log.info("Migration: migrating %d datasets to user library", len(to_migrate))

    for ds_id, filename, disk_path, project_id, user_id in to_migrate:
        # Set user_id
        await conn.execute(text(
            "UPDATE datasets SET user_id = :uid WHERE id = :did"
        ), {"uid": user_id, "did": ds_id})

        # Create junction entry if not exists
        r = await conn.execute(text(
            "SELECT 1 FROM project_datasets "
            "WHERE project_id = :pid AND dataset_id = :did"
        ), {"pid": project_id, "did": ds_id})
        if not r.scalar():
            role = _infer_role(filename)
            link_id = secrets.token_hex(6)
            await conn.execute(text(
                "INSERT INTO project_datasets (id, project_id, dataset_id, role, assigned_at) "
                "VALUES (:id, :pid, :did, :role, NOW())"
            ), {"id": link_id, "pid": project_id, "did": ds_id, "role": role})

        # Copy file to user-level storage
        old_path = Path(disk_path)
        if old_path.exists():
            new_dir = settings.data_dir / "datasets" / user_id
            new_dir.mkdir(parents=True, exist_ok=True)
            new_path = new_dir / f"{ds_id}_{filename}"
            if not new_path.exists():
                shutil.copy2(old_path, new_path)
            await conn.execute(text(
                "UPDATE datasets SET disk_path = :path WHERE id = :did"
            ), {"path": str(new_path), "did": ds_id})

        _log.info("  Migrated dataset %s (%s) → user %s", ds_id, filename, user_id)

    # Record migration
    try:
        await conn.execute(text(
            "INSERT INTO schema_versions (version, applied_at) "
            "VALUES ('v2_dataset_library', NOW()) ON CONFLICT DO NOTHING"
        ))
    except Exception:
        pass
    _log.info("Migration v2_dataset_library complete")


async def _migrate_to_composite_datasets(conn):
    """Migrate single-file datasets to composite dataset groups (v3).

    Creates dataset_files records from old datasets, groups per-project
    datasets into single composite datasets, and adds missing columns
    to projects/datasets tables.  Idempotent.
    """
    # Check if already applied
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v3_composite_datasets'")
        )
        if r.scalar():
            return
    except Exception:
        pass

    _log.info("Migration v3: composite datasets — starting")

    # ── 0. Widen id columns from VARCHAR(8) to VARCHAR(12) ────────────
    # The old schema used 8-char IDs; the new model uses 12-char IDs.
    widen_cols = [
        ("users", "id"), ("projects", "id"), ("projects", "user_id"),
        ("datasets", "id"), ("datasets", "user_id"),
        ("project_datasets", "id"), ("project_datasets", "project_id"),
        ("project_datasets", "dataset_id"),
        ("jobs", "id"), ("jobs", "project_id"),
        ("project_shares", "id"), ("project_shares", "project_id"),
        ("project_shares", "user_id"), ("project_shares", "shared_by"),
        ("schema_versions", "version"),
    ]
    for tbl, col in widen_cols:
        try:
            r = await conn.execute(text(
                "SELECT character_maximum_length FROM information_schema.columns "
                "WHERE table_name = :tbl AND column_name = :col"
            ), {"tbl": tbl, "col": col})
            max_len = r.scalar()
            if max_len is not None and max_len < 12 and col != "version":
                await conn.execute(text(
                    f"ALTER TABLE {tbl} ALTER COLUMN {col} TYPE VARCHAR(12)"
                ))
                _log.info("  Widened %s.%s from VARCHAR(%s) to VARCHAR(12)", tbl, col, max_len)
        except Exception as e:
            _log.debug("  Skip widening %s.%s: %s", tbl, col, e)

    # ── 0b. Make old datasets columns nullable (they'll be dropped later) ─
    for old_col in ("project_id", "filename", "disk_path", "uploaded_at"):
        try:
            r = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'datasets' AND column_name = :col"
            ), {"col": old_col})
            if r.scalar():
                await conn.execute(text(
                    f"ALTER TABLE datasets ALTER COLUMN {old_col} DROP NOT NULL"
                ))
        except Exception as e:
            _log.debug("  Skip nullable %s: %s", old_col, e)

    # Also make project_datasets.role nullable (column being removed)
    try:
        r = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'project_datasets' AND column_name = 'role'"
        ))
        if r.scalar():
            await conn.execute(text(
                "ALTER TABLE project_datasets ALTER COLUMN role DROP NOT NULL"
            ))
    except Exception:
        pass

    # ── 1. Add missing columns ──────────────────────────────────────────

    # datasets.name
    r = await conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'datasets' AND column_name = 'name'"
    ))
    if not r.scalar():
        await conn.execute(text("ALTER TABLE datasets ADD COLUMN name VARCHAR(255)"))

    # datasets.created_at (old schema had uploaded_at)
    r = await conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'datasets' AND column_name = 'created_at'"
    ))
    if not r.scalar():
        await conn.execute(text(
            "ALTER TABLE datasets ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()"
        ))
        r2 = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'datasets' AND column_name = 'uploaded_at'"
        ))
        if r2.scalar():
            await conn.execute(text(
                "UPDATE datasets SET created_at = uploaded_at WHERE created_at IS NULL"
            ))

    # projects.description
    r = await conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'projects' AND column_name = 'description'"
    ))
    if not r.scalar():
        await conn.execute(text(
            "ALTER TABLE projects ADD COLUMN description VARCHAR(500) DEFAULT ''"
        ))

    # projects.updated_at
    r = await conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'projects' AND column_name = 'updated_at'"
    ))
    if not r.scalar():
        await conn.execute(text(
            "ALTER TABLE projects ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE"
        ))

    # ── 2. Check if old-style datasets exist (have filename column) ─────

    r = await conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'datasets' AND column_name = 'filename'"
    ))
    has_filename_col = r.scalar() is not None

    if not has_filename_col:
        # Fresh install — nothing to migrate
        await conn.execute(text(
            "INSERT INTO schema_versions (version, applied_at) "
            "VALUES ('v3_composite_datasets', NOW()) ON CONFLICT DO NOTHING"
        ))
        _log.info("Migration v3: fresh install, nothing to migrate")
        return

    # Check if any old-style datasets need migration
    rows = await conn.execute(text(
        "SELECT d.id, d.filename, d.disk_path, d.user_id "
        "FROM datasets d "
        "WHERE d.filename IS NOT NULL AND d.filename != '' "
        "AND NOT EXISTS (SELECT 1 FROM dataset_files df WHERE df.dataset_id = d.id)"
    ))
    old_datasets = rows.fetchall()

    if not old_datasets:
        await conn.execute(text(
            "INSERT INTO schema_versions (version, applied_at) "
            "VALUES ('v3_composite_datasets', NOW()) ON CONFLICT DO NOTHING"
        ))
        _log.info("Migration v3: no old-style datasets to migrate")
        return

    _log.info("Migration v3: migrating %d old-style datasets", len(old_datasets))
    old_ds_map = {r[0]: (r[1], r[2], r[3]) for r in old_datasets}

    # ── 3. Group datasets by project ────────────────────────────────────

    from collections import defaultdict

    pd_rows = await conn.execute(text(
        "SELECT pd.project_id, pd.dataset_id, pd.role, p.name AS project_name, p.user_id "
        "FROM project_datasets pd "
        "JOIN projects p ON pd.project_id = p.id"
    ))
    assignments = pd_rows.fetchall()

    project_groups = defaultdict(list)    # project_id -> [(ds_id, role, proj_name, user_id)]
    assigned_dataset_ids = set()
    for proj_id, ds_id, role, proj_name, user_id in assignments:
        project_groups[proj_id].append((ds_id, role, proj_name, user_id))
        assigned_dataset_ids.add(ds_id)

    # ── 4. For each project, create ONE composite dataset ───────────────

    for proj_id, group in project_groups.items():
        if not group:
            continue
        proj_name = group[0][2]
        user_id = group[0][3]

        new_ds_id = secrets.token_hex(6)
        await conn.execute(text(
            "INSERT INTO datasets (id, name, description, user_id, created_at) "
            "VALUES (:id, :name, '', :uid, NOW())"
        ), {"id": new_ds_id, "name": proj_name, "uid": user_id})

        for ds_id, role, _, _ in group:
            if ds_id not in old_ds_map:
                continue
            filename, disk_path, _ = old_ds_map[ds_id]
            if not filename:
                continue
            file_id = secrets.token_hex(6)
            await conn.execute(text(
                "INSERT INTO dataset_files (id, dataset_id, filename, role, disk_path, uploaded_at) "
                "VALUES (:id, :dsid, :fn, :role, :dp, NOW())"
            ), {"id": file_id, "dsid": new_ds_id, "fn": filename, "role": role, "dp": disk_path or ""})

        # Replace old links with one link to the composite
        await conn.execute(text(
            "DELETE FROM project_datasets WHERE project_id = :pid"
        ), {"pid": proj_id})
        link_id = secrets.token_hex(6)
        await conn.execute(text(
            "INSERT INTO project_datasets (id, project_id, dataset_id, assigned_at) "
            "VALUES (:id, :pid, :did, NOW())"
        ), {"id": link_id, "pid": proj_id, "did": new_ds_id})

        _log.info("  Project '%s': grouped %d files → composite %s", proj_name, len(group), new_ds_id)

    # ── 5. Handle orphan datasets (not assigned to any project) ─────────

    for ds_id, (filename, disk_path, user_id) in old_ds_map.items():
        if ds_id in assigned_dataset_ids:
            continue
        # Convert in-place: set name, create a DatasetFile
        await conn.execute(text(
            "UPDATE datasets SET name = :name WHERE id = :id AND (name IS NULL OR name = '')"
        ), {"name": filename, "id": ds_id})
        file_id = secrets.token_hex(6)
        role = _infer_role(filename) if filename else None
        await conn.execute(text(
            "INSERT INTO dataset_files (id, dataset_id, filename, role, disk_path, uploaded_at) "
            "VALUES (:id, :dsid, :fn, :role, :dp, NOW())"
        ), {"id": file_id, "dsid": ds_id, "fn": filename, "role": role, "dp": disk_path or ""})
        _log.info("  Orphan dataset %s (%s): converted to single-file group", ds_id, filename)

    # ── 6. Clean up old assigned datasets ───────────────────────────────

    for ds_id in assigned_dataset_ids:
        r = await conn.execute(text(
            "SELECT 1 FROM project_datasets WHERE dataset_id = :did"
        ), {"did": ds_id})
        if not r.scalar():
            await conn.execute(text("DELETE FROM datasets WHERE id = :id"), {"id": ds_id})

    # ── 7. Drop old columns that are no longer part of the model ────────
    for old_col in ("project_id", "filename", "disk_path", "uploaded_at"):
        try:
            r = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'datasets' AND column_name = :col"
            ), {"col": old_col})
            if r.scalar():
                # Drop FK constraint on project_id first if present
                if old_col == "project_id":
                    try:
                        await conn.execute(text(
                            "ALTER TABLE datasets DROP CONSTRAINT IF EXISTS datasets_project_id_fkey"
                        ))
                    except Exception:
                        pass
                await conn.execute(text(f"ALTER TABLE datasets DROP COLUMN {old_col}"))
                _log.info("  Dropped datasets.%s", old_col)
        except Exception as e:
            _log.debug("  Skip drop datasets.%s: %s", old_col, e)

    # Drop old role column from project_datasets
    try:
        r = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'project_datasets' AND column_name = 'role'"
        ))
        if r.scalar():
            await conn.execute(text("ALTER TABLE project_datasets DROP COLUMN role"))
            _log.info("  Dropped project_datasets.role")
    except Exception:
        pass

    # Record migration
    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v3_composite_datasets', NOW()) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v3_composite_datasets complete")


async def _migrate_add_admin_flag(conn):
    """v4: Add is_admin column to users. Idempotent."""
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v4_admin_flag'")
        )
        if r.scalar():
            return
    except Exception:
        pass

    _log.info("Migration v4: admin flag — starting")

    # Add is_admin column if missing
    try:
        r = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'is_admin'"
        ))
        if not r.scalar():
            await conn.execute(text(
                "ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE"
            ))
            _log.info("  Added users.is_admin column")
    except Exception:
        # SQLite: column created by Base.metadata.create_all
        pass

    # Account seeding is not a schema concern: see _bootstrap_accounts().
    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v4_admin_flag', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v4_admin_flag complete")


async def _migrate_add_job_name(conn):
    """v5: Add name column to jobs table. Idempotent."""
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v5_job_name'")
        )
        if r.scalar():
            return
    except Exception:
        pass

    _log.info("Migration v5: job name — starting")

    try:
        r = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'jobs' AND column_name = 'name'"
        ))
        if not r.scalar():
            await conn.execute(text(
                "ALTER TABLE jobs ADD COLUMN name VARCHAR(255)"
            ))
            _log.info("  Added jobs.name column")
    except Exception:
        pass

    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v5_job_name', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v5_job_name complete")


async def _migrate_add_job_user_id(conn):
    """v6: Add user_id FK to jobs table for tracking who launched each job."""
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v6_job_user_id'")
        )
        if r.scalar():
            return
    except Exception:
        pass

    _log.info("Migration v6: job user_id — starting")

    try:
        r = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'jobs' AND column_name = 'user_id'"
        ))
        if not r.scalar():
            await conn.execute(text(
                "ALTER TABLE jobs ADD COLUMN user_id VARCHAR(12) REFERENCES users(id) ON DELETE SET NULL"
            ))
            _log.info("  Added jobs.user_id column")
    except Exception:
        pass

    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v6_job_user_id', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v6_job_user_id complete")


async def _migrate_add_job_config_hash(conn):
    """v7: Add config_hash column to jobs for duplicate detection."""
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v7_job_config_hash'")
        )
        if r.scalar():
            return
    except Exception:
        pass

    _log.info("Migration v7: job config_hash — starting")

    try:
        r = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'jobs' AND column_name = 'config_hash'"
        ))
        if not r.scalar():
            await conn.execute(text(
                "ALTER TABLE jobs ADD COLUMN config_hash VARCHAR(32)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_jobs_config_hash ON jobs (config_hash)"
            ))
            _log.info("  Added jobs.config_hash column with index")
    except Exception:
        pass

    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v7_job_config_hash', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v7_job_config_hash complete")


async def _migrate_add_job_disk_size(conn):
    """v8: Add disk_size_bytes column to jobs for cached disk usage."""
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v8_job_disk_size'")
        )
        if r.scalar():
            return
    except Exception:
        pass

    _log.info("Migration v8: job disk_size_bytes — starting")

    try:
        r = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'jobs' AND column_name = 'disk_size_bytes'"
        ))
        if not r.scalar():
            await conn.execute(text(
                "ALTER TABLE jobs ADD COLUMN disk_size_bytes BIGINT"
            ))
            _log.info("  Added jobs.disk_size_bytes column")
    except Exception:
        pass

    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v8_job_disk_size', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v8_job_disk_size complete")


async def _migrate_add_dataset_tags(conn):
    """v9: Add tags JSON column to datasets."""
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v9_dataset_tags'")
        )
        if r.scalar():
            return
    except Exception:
        pass

    _log.info("Migration v9: dataset tags — starting")

    try:
        r = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'datasets' AND column_name = 'tags'"
        ))
        if not r.scalar():
            await conn.execute(text(
                "ALTER TABLE datasets ADD COLUMN tags JSON DEFAULT '[]'"
            ))
            _log.info("  Added datasets.tags column")
    except Exception:
        pass

    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v9_dataset_tags', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v9_dataset_tags complete")


async def _migrate_add_job_batch_id(conn):
    """v10: Add batch_id column to jobs for batch run grouping."""
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v10_job_batch_id'")
        )
        if r.scalar():
            return
    except Exception:
        pass

    _log.info("Migration v10: job batch_id — starting")

    try:
        r = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'jobs' AND column_name = 'batch_id'"
        ))
        if not r.scalar():
            await conn.execute(text(
                "ALTER TABLE jobs ADD COLUMN batch_id VARCHAR(12)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_jobs_batch_id ON jobs (batch_id)"
            ))
            _log.info("  Added jobs.batch_id column with index")
    except Exception:
        pass

    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v10_job_batch_id', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v10_job_batch_id complete")


async def _migrate_add_audit_log(conn):
    """v11: Create audit_logs table."""
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v11_audit_log'")
        )
        if r.scalar():
            return
    except Exception:
        pass
    _log.info("Migration v11: audit log — starting")
    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v11_audit_log', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v11_audit_log complete")


async def _migrate_add_password_reset(conn):
    """v12: Add password_reset_tokens table and email_verified column."""
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v12_password_reset'")
        )
        if r.scalar():
            return
    except Exception:
        pass
    _log.info("Migration v12: password reset — starting")
    # Add email_verified column to users if missing
    r = await conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'users' AND column_name = 'email_verified'"
    ))
    if not r.scalar():
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE"
        ))
    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v12_password_reset', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v12_password_reset complete")


async def _migrate_add_api_keys(conn):
    """v13: Create api_keys table."""
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v13_api_keys'")
        )
        if r.scalar():
            return
    except Exception:
        pass
    _log.info("Migration v13: api keys — starting")
    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v13_api_keys', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v13_api_keys complete")


async def _migrate_add_webhooks(conn):
    """v14: Create webhooks table."""
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v14_webhooks'")
        )
        if r.scalar():
            return
    except Exception:
        pass
    _log.info("Migration v14: webhooks — starting")
    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v14_webhooks', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v14_webhooks complete")


async def _migrate_add_dataset_versions(conn):
    """v15: Create dataset_versions table."""
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v15_dataset_versions'")
        )
        if r.scalar():
            return
    except Exception:
        pass
    _log.info("Migration v15: dataset versions — starting")
    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v15_dataset_versions', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v15_dataset_versions complete")


async def _migrate_add_job_best_auc(conn):
    """v16: Add best_auc and best_k columns to jobs for fast list_jobs."""
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v16_job_best_auc'")
        )
        if r.scalar():
            return
    except Exception:
        pass

    _log.info("Migration v16: job best_auc/best_k — starting")

    for col, col_type in [("best_auc", "FLOAT"), ("best_k", "INTEGER")]:
        try:
            r = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'jobs' AND column_name = :col"
            ), {"col": col})
            if not r.scalar():
                await conn.execute(text(
                    f"ALTER TABLE jobs ADD COLUMN {col} {col_type}"
                ))
                _log.info("  Added jobs.%s column", col)
        except Exception:
            pass

    # Backfill from results.json files for existing completed jobs
    try:
        rows = await conn.execute(text(
            "SELECT id, project_id FROM jobs "
            "WHERE status = 'completed' AND best_auc IS NULL"
        ))
        to_backfill = rows.fetchall()
        if to_backfill:
            _log.info("  Backfilling best_auc/best_k for %d completed jobs", len(to_backfill))
            import json as _json
            for job_id, project_id in to_backfill:
                results_path = Path(settings.project_dir) / project_id / "jobs" / job_id / "results.json"
                if results_path.exists():
                    try:
                        with open(results_path) as rf:
                            res = _json.load(rf)
                        best = res.get("best_individual", {})
                        auc = best.get("auc")
                        k = best.get("k")
                        if auc is not None or k is not None:
                            await conn.execute(text(
                                "UPDATE jobs SET best_auc = :auc, best_k = :k WHERE id = :id"
                            ), {"auc": auc, "k": k, "id": job_id})
                    except Exception:
                        pass
    except Exception as e:
        _log.warning("  Backfill skipped: %s", e)

    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v16_job_best_auc', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v16_job_best_auc complete")


async def _migrate_add_project_comments(conn):
    """v17: Create project_comments table."""
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v17_project_comments'")
        )
        if r.scalar():
            return
    except Exception:
        pass

    _log.info("Migration v17: project_comments — starting")
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS project_comments (
            id VARCHAR(12) PRIMARY KEY,
            project_id VARCHAR(12) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            user_id VARCHAR(12) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE
        )
    """))
    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v17_project_comments', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v17_project_comments complete")


async def _migrate_add_public_shares(conn):
    """v18: Create public_shares table."""
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v18_public_shares'")
        )
        if r.scalar():
            return
    except Exception:
        pass

    _log.info("Migration v18: public_shares — starting")
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS public_shares (
            id VARCHAR(12) PRIMARY KEY,
            project_id VARCHAR(12) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            token VARCHAR(64) NOT NULL UNIQUE,
            created_by VARCHAR(12) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TIMESTAMP WITH TIME ZONE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_public_shares_token ON public_shares(token)"
    ))
    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v18_public_shares', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v18_public_shares complete")


async def _migrate_add_project_class_names(conn):
    """v19: Add class_names JSON column to projects."""
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v19_project_class_names'")
        )
        if r.scalar():
            return
    except Exception:
        pass

    _log.info("Migration v19: project class_names — starting")
    try:
        r = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'projects' AND column_name = 'class_names'"
        ))
        if not r.scalar():
            await conn.execute(text(
                "ALTER TABLE projects ADD COLUMN class_names JSON"
            ))
            _log.info("  Added projects.class_names column")
    except Exception:
        pass
    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v19_project_class_names', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v19_project_class_names complete")


async def _migrate_add_dataset_archived(conn):
    """v20: Add archived boolean column to datasets."""
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v20_dataset_archived'")
        )
        if r.scalar():
            return
    except Exception:
        pass

    _log.info("Migration v20: dataset archived — starting")
    try:
        r = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'datasets' AND column_name = 'archived'"
        ))
        if not r.scalar():
            await conn.execute(text(
                "ALTER TABLE datasets ADD COLUMN archived BOOLEAN DEFAULT FALSE"
            ))
            _log.info("  Added datasets.archived column")
    except Exception:
        pass
    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v20_dataset_archived', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v20_dataset_archived complete")


async def _migrate_add_dataset_metadata(conn):
    """v21: Add metadata JSON column to datasets."""
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v21_dataset_data_meta'")
        )
        if r.scalar():
            return
    except Exception:
        pass

    _log.info("Migration v21: dataset metadata — starting")
    try:
        r = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'datasets' AND column_name = 'data_meta'"
        ))
        if not r.scalar():
            await conn.execute(text(
                "ALTER TABLE datasets ADD COLUMN data_meta JSON"
            ))
            _log.info("  Added datasets.data_meta column")
    except Exception:
        pass
    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v21_dataset_data_meta', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v21_dataset_data_meta complete")


async def _migrate_add_scitq_task_id(conn):
    """v22: Add scitq_task_id column to jobs for distributed task queue integration."""
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v22_scitq_task_id'")
        )
        if r.scalar():
            return
    except Exception:
        pass

    _log.info("Migration v22: scitq_task_id — starting")
    try:
        r = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'jobs' AND column_name = 'scitq_task_id'"
        ))
        if not r.scalar():
            await conn.execute(text(
                "ALTER TABLE jobs ADD COLUMN scitq_task_id INTEGER"
            ))
            _log.info("  Added jobs.scitq_task_id column")
    except Exception:
        pass
    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v22_scitq_task_id', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v22_scitq_task_id complete")


async def _migrate_add_project_archived(conn):
    """v23: Add archived boolean column to projects."""
    try:
        r = await conn.execute(
            text("SELECT 1 FROM schema_versions WHERE version = 'v23_project_archived'")
        )
        if r.scalar():
            return
    except Exception:
        pass

    _log.info("Migration v23: project archived — starting")
    try:
        r = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'projects' AND column_name = 'archived'"
        ))
        if not r.scalar():
            await conn.execute(text(
                "ALTER TABLE projects ADD COLUMN archived BOOLEAN DEFAULT FALSE"
            ))
            _log.info("  Added projects.archived column")
    except Exception:
        pass
    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v23_project_archived', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v23_project_archived complete")


async def _migrate_job_runtime_and_indexes(conn):
    """v24: jobs.started_at / jobs.pid, plus indexes on foreign keys and jobs.status.

    PostgreSQL does not index foreign keys by itself; these back the per-project
    and per-user lookups made on almost every request. Fresh databases get all of
    this from the models, so the statements only matter when upgrading.
    """
    r = await conn.execute(text("SELECT 1 FROM schema_versions WHERE version = 'v24_job_runtime_indexes'"))
    if r.scalar():
        return
    _log.info("Migration v24: job runtime columns and indexes — starting")
    if conn.dialect.name == "postgresql":
        await conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE"))
        await conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS pid INTEGER"))
        for name, table, column in _V24_INDEXES:
            await conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({column})"))
    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v24_job_runtime_indexes', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v24_job_runtime_indexes complete")


_V24_INDEXES = [
    ("ix_projects_user_id", "projects", "user_id"),
    ("ix_datasets_user_id", "datasets", "user_id"),
    ("ix_dataset_files_dataset_id", "dataset_files", "dataset_id"),
    ("ix_project_datasets_project_id", "project_datasets", "project_id"),
    ("ix_project_datasets_dataset_id", "project_datasets", "dataset_id"),
    ("ix_jobs_project_id", "jobs", "project_id"),
    ("ix_jobs_user_id", "jobs", "user_id"),
    ("ix_jobs_status", "jobs", "status"),
    ("ix_project_shares_project_id", "project_shares", "project_id"),
    ("ix_project_shares_user_id", "project_shares", "user_id"),
    ("ix_audit_logs_user_id", "audit_logs", "user_id"),
    ("ix_password_reset_tokens_user_id", "password_reset_tokens", "user_id"),
    ("ix_api_keys_user_id", "api_keys", "user_id"),
    ("ix_webhooks_user_id", "webhooks", "user_id"),
    ("ix_project_comments_project_id", "project_comments", "project_id"),
    ("ix_project_comments_user_id", "project_comments", "user_id"),
    ("ix_public_shares_project_id", "public_shares", "project_id"),
    ("ix_public_shares_created_by", "public_shares", "created_by"),
    ("ix_dataset_versions_dataset_id", "dataset_versions", "dataset_id"),
]


LEGACY_MIGRATIONS = [
    _migrate_datasets_to_user_library,
    _migrate_to_composite_datasets,
    _migrate_add_admin_flag,
    _migrate_add_job_name,
    _migrate_add_job_user_id,
    _migrate_add_job_config_hash,
    _migrate_add_job_disk_size,
    _migrate_add_dataset_tags,
    _migrate_add_job_batch_id,
    _migrate_add_audit_log,
    _migrate_add_password_reset,
    _migrate_add_api_keys,
    _migrate_add_webhooks,
    _migrate_add_dataset_versions,
    _migrate_add_job_best_auc,
    _migrate_add_project_comments,
    _migrate_add_public_shares,
    _migrate_add_project_class_names,
    _migrate_add_dataset_archived,
    _migrate_add_dataset_metadata,
    _migrate_add_scitq_task_id,
    _migrate_add_project_archived,
    _migrate_job_runtime_and_indexes,
]

# Versions recorded in ``schema_versions`` once every legacy migration has run.
LEGACY_VERSIONS = [
    "v2_dataset_library", "v3_composite_datasets", "v4_admin_flag", "v5_job_name",
    "v6_job_user_id", "v7_job_config_hash", "v8_job_disk_size", "v9_dataset_tags",
    "v10_job_batch_id", "v11_audit_log", "v12_password_reset", "v13_api_keys",
    "v14_webhooks", "v15_dataset_versions", "v16_job_best_auc", "v17_project_comments",
    "v18_public_shares", "v19_project_class_names", "v20_dataset_archived",
    "v21_dataset_data_meta", "v22_scitq_task_id", "v23_project_archived",
    "v24_job_runtime_indexes",
]


async def run_legacy_migrations(conn) -> None:
    """Run every pre-Alembic migration on ``conn`` (an AsyncConnection in a transaction).

    Each one is idempotent and skips itself when its ``schema_versions`` row
    exists. Any error that a migration does not handle itself propagates, so the
    caller's transaction is rolled back as a whole.
    """
    guarded = SavepointConnection(conn)
    for migration in LEGACY_MIGRATIONS:
        try:
            await migration(guarded)
        except Exception:
            _log.exception("Legacy migration %s failed", migration.__name__)
            raise
