"""PredomicsApp FastAPI application."""

import logging
import secrets
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .core.config import settings
from .core.database import engine, Base
from .models import db_models  # noqa: F401 — ensure models are registered
from .routers import health, projects, analysis, auth, samples, datasets, sharing, admin
from .routers.datasets import _infer_role
from .services.storage import ensure_dirs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

_log = logging.getLogger(__name__)


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
    """v4: Add is_admin column to users, seed admin + demo user. Idempotent."""
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

    # Promote prifti to admin
    await conn.execute(text(
        "UPDATE users SET is_admin = TRUE WHERE email LIKE '%prifti%'"
    ))

    # Seed demo user if not exists
    from .core.security import hash_password
    r = await conn.execute(text(
        "SELECT 1 FROM users WHERE email = 'demo@predomics.com'"
    ))
    if not r.scalar():
        import uuid
        demo_id = uuid.uuid4().hex[:12]
        demo_pw = hash_password("demo")
        await conn.execute(text(
            "INSERT INTO users (id, email, hashed_password, full_name, is_active, is_admin, created_at) "
            "VALUES (:id, :email, :pw, :name, TRUE, FALSE, CURRENT_TIMESTAMP)"
        ), {
            "id": demo_id,
            "email": "demo@predomics.com",
            "pw": demo_pw,
            "name": "Demo User",
        })
        _log.info("  Created demo user: demo@predomics.com / demo")

    await conn.execute(text(
        "INSERT INTO schema_versions (version, applied_at) "
        "VALUES ('v4_admin_flag', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
    ))
    _log.info("Migration v4_admin_flag complete")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown events."""
    ensure_dirs()
    # Create database tables (for dev; use Alembic migrations in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Run migrations for existing databases
    async with engine.begin() as conn:
        await _migrate_datasets_to_user_library(conn)
    async with engine.begin() as conn:
        await _migrate_to_composite_datasets(conn)
    async with engine.begin() as conn:
        await _migrate_add_admin_flag(conn)
    _log.info("PredomicsApp started — data_dir=%s", settings.data_dir)
    yield


app = FastAPI(
    title="PredomicsApp API",
    description="Web API for gpredomics — sparse interpretable ML model discovery",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for Vue.js dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
app.include_router(admin.router, prefix="/api")

# Serve Vue.js frontend (production: built into backend/static/)
_static_dir = Path(__file__).parent / "static"
if _static_dir.is_dir():
    from fastapi.responses import FileResponse

    app.mount("/assets", StaticFiles(directory=_static_dir / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve Vue.js SPA — all non-API routes return index.html."""
        file_path = _static_dir / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_static_dir / "index.html")
