"""Schema migrations (audit BE-8 / OPS-10).

The SQLite tests always run. The PostgreSQL tests need a server and run when
``PREDOMICS_TEST_PG_URL`` is set (a SQLAlchemy URL whose user may create
databases, e.g. ``postgresql+asyncpg://predomics:predomics@localhost:5432/predomics``);
each one works in its own scratch database.

``migrate`` is exercised the way an operator runs it — as ``python -m app.migrate``
in a subprocess with ``PREDOMICS_DATABASE_URL`` pointing at the scratch database.
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

BACKEND = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "legacy_v23_schema.sql"
PG_URL = os.environ.get("PREDOMICS_TEST_PG_URL", "")
HEAD = "0002_normalize_schema"

needs_pg = pytest.mark.skipif(not PG_URL, reason="set PREDOMICS_TEST_PG_URL to run PostgreSQL migration tests")


def _migrate(database_url: str, *args: str, tmp_path: Path, extra_env: dict | None = None):
    env = {
        **os.environ,
        "PREDOMICS_DATABASE_URL": database_url,
        "PREDOMICS_DATA_DIR": str(tmp_path / "data"),
        "PYTHONPATH": str(BACKEND),
        **(extra_env or {}),
    }
    return subprocess.run(
        [sys.executable, "-m", "app.migrate", *args],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=180,
    )


def _ok(result):
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr[-3000:]}"
    return result


# ---------------------------------------------------------------------------
# SQLite (development databases)
# ---------------------------------------------------------------------------

class TestSqlite:
    def test_new_database_is_created_and_stamped_at_head(self, tmp_path):
        url = f"sqlite+aiosqlite:///{tmp_path / 'dev.db'}"
        _ok(_migrate(url, tmp_path=tmp_path))
        status = _ok(_migrate(url, "status", tmp_path=tmp_path)).stdout
        assert f"revision={HEAD}" in status and "up_to_date=True" in status
        engine = sa.create_engine(f"sqlite:///{tmp_path / 'dev.db'}")
        with engine.connect() as conn:
            tables = set(sa.inspect(conn).get_table_names())
            assert {"users", "jobs", "project_datasets", "alembic_version"} <= tables
            assert "email_verify_token_hash" in {c["name"] for c in sa.inspect(conn).get_columns("users")}

    def test_running_twice_is_a_no_op(self, tmp_path):
        url = f"sqlite+aiosqlite:///{tmp_path / 'dev.db'}"
        _ok(_migrate(url, tmp_path=tmp_path))
        second = _ok(_migrate(url, tmp_path=tmp_path))
        assert HEAD in second.stdout

    def test_revisions_replay_on_sqlite(self, tmp_path):
        """`alembic upgrade head` from nothing works on SQLite too (batch mode)."""
        from alembic import command
        from alembic.config import Config
        from alembic.migration import MigrationContext

        engine = sa.create_engine(f"sqlite:///{tmp_path / 'replay.db'}")
        with engine.begin() as conn:
            cfg = Config(str(BACKEND / "alembic.ini"))
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "0001_baseline")
            conn.execute(sa.text(
                "INSERT INTO users (id, email, hashed_password, full_name, is_active, is_admin, created_at) "
                "VALUES ('u1', 'a@example.com', 'x', 'A', 1, 0, CURRENT_TIMESTAMP)"
            ))
            command.upgrade(cfg, "head")
            assert MigrationContext.configure(conn).get_current_revision() == HEAD
            row = conn.execute(sa.text("SELECT email, email_verified FROM users")).one()
            assert row.email == "a@example.com" and bool(row.email_verified) is True
            uniques = {tuple(u["column_names"]) for u in sa.inspect(conn).get_unique_constraints("project_shares")}
            assert ("project_id", "user_id") in uniques

    def test_auto_migrate_off_refuses_an_outdated_database(self, tmp_path):
        url = f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}"
        code = (
            "import asyncio, app.migrate as m\n"
            "assert m.auto_migrate_enabled() is False\n"
            "asyncio.run(m.require_up_to_date())\n"
        )
        env = {**os.environ, "PREDOMICS_DATABASE_URL": url, "PREDOMICS_AUTO_MIGRATE": "false",
               "PREDOMICS_DATA_DIR": str(tmp_path / "data"), "PYTHONPATH": str(BACKEND)}
        result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env,
                                capture_output=True, text=True, timeout=120)
        assert result.returncode != 0
        assert "python -m backend.app.migrate" in result.stderr


def test_frozen_schema_of_latest_revision_matches_models():
    """A model change without a revision (and a frozen-schema update) fails here."""
    import importlib.util

    from app.core.database import Base
    from app.models import db_models  # noqa: F401

    spec = importlib.util.spec_from_file_location("frozen_schema", BACKEND / "alembic" / "frozen_schema.py")
    frozen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(frozen)
    latest = frozen.build(99)

    def shape(metadata):
        out = {}
        for table in metadata.sorted_tables:
            out[table.name] = {
                "columns": {
                    c.name: (type(c.type).__name__, getattr(c.type, "length", None), c.nullable,
                             c.primary_key, sorted(fk.target_fullname for fk in c.foreign_keys))
                    for c in table.columns
                },
                "indexes": sorted((i.name, tuple(c.name for c in i.columns), bool(i.unique)) for i in table.indexes),
                "uniques": sorted(tuple(c.name for c in k.columns) for k in table.constraints
                                  if isinstance(k, sa.UniqueConstraint)),
            }
        return out

    assert shape(latest) == shape(Base.metadata), (
        "The models differ from the frozen schema of the latest Alembic revision. "
        "Add a revision and update backend/alembic/frozen_schema.py."
    )


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------

@pytest.fixture
def pg_database():
    """A scratch PostgreSQL database; yields (async URL, sync URL)."""
    base = sa.engine.make_url(PG_URL)
    admin_url = base.set(drivername="postgresql+psycopg2")
    name = f"predomics_mig_{uuid.uuid4().hex[:10]}"
    admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=sa.pool.NullPool)
    with admin.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
    try:
        yield (
            base.set(drivername="postgresql+asyncpg", database=name).render_as_string(hide_password=False),
            admin_url.set(database=name).render_as_string(hide_password=False),
        )
    finally:
        with admin.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _load_legacy(sync_url: str, with_duplicates: bool = False):
    """Build a pre-Alembic (v23) database: real schema, synthetic rows."""
    engine = sa.create_engine(sync_url, poolclass=sa.pool.NullPool)
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute(FIXTURE.read_text())
        raw.commit()
    finally:
        raw.close()
    with engine.begin() as conn:
        conn.execute(sa.text("SET search_path TO public"))
        conn.execute(sa.text(
            "INSERT INTO users (id, email, hashed_password, full_name, is_active, created_at, is_admin) VALUES "
            "('u1', 'owner@example.com', 'h', 'Owner', TRUE, now(), TRUE), "
            "('u2', 'guest@example.com', 'h', 'Guest', TRUE, now(), NULL)"
        ))
        conn.execute(sa.text(
            "INSERT INTO projects (id, name, description, user_id, created_at) VALUES "
            "('p1', 'Project', NULL, 'u1', now())"
        ))
        conn.execute(sa.text(
            "INSERT INTO datasets (id, user_id, name, description, created_at, archived) VALUES "
            "('d1', 'u1', 'Data', NULL, NULL, NULL)"
        ))
        conn.execute(sa.text(
            "INSERT INTO dataset_files (id, dataset_id, filename, role, disk_path, uploaded_at) VALUES "
            "('f1', 'd1', 'X.tsv', 'xtrain', '/nowhere/X.tsv', now())"
        ))
        conn.execute(sa.text(
            "INSERT INTO project_datasets (id, project_id, dataset_id, assigned_at) VALUES ('l1', 'p1', 'd1', now())"
        ))
        conn.execute(sa.text(
            "INSERT INTO project_shares (id, project_id, user_id, role, shared_at) VALUES "
            "('s1', 'p1', 'u2', 'viewer', now())"
        ))
        conn.execute(sa.text(
            "INSERT INTO jobs (id, project_id, user_id, status, created_at, disk_size_bytes) VALUES "
            "('j1', 'p1', 'u1', 'completed', now(), 5000000000)"
        ))
        if with_duplicates:
            conn.execute(sa.text(
                "INSERT INTO project_datasets (id, project_id, dataset_id, assigned_at) VALUES ('l2', 'p1', 'd1', now())"
            ))
            conn.execute(sa.text(
                "INSERT INTO project_shares (id, project_id, user_id, role, shared_at) VALUES "
                "('s2', 'p1', 'u2', 'editor', now())"
            ))
    engine.dispose()


@needs_pg
class TestPostgres:
    def test_fresh_database_matches_models(self, pg_database, tmp_path):
        url, sync_url = pg_database
        _ok(_migrate(url, tmp_path=tmp_path))
        check = _migrate(url, "check", tmp_path=tmp_path)
        assert check.returncode == 0, check.stdout
        assert "Schema matches the models." in check.stdout
        with sa.create_engine(sync_url).connect() as conn:
            assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() == HEAD
            assert conn.execute(sa.text("SELECT count(*) FROM schema_versions")).scalar() == 23

    def test_legacy_database_is_adopted_with_data_intact(self, pg_database, tmp_path):
        url, sync_url = pg_database
        _load_legacy(sync_url, with_duplicates=True)

        status = _migrate(url, "status", tmp_path=tmp_path)
        assert status.returncode == 1 and "state=legacy" in status.stdout
        assert HEAD in _ok(_migrate(url, tmp_path=tmp_path)).stdout
        check = _migrate(url, "check", tmp_path=tmp_path)
        assert check.returncode == 0, check.stdout

        with sa.create_engine(sync_url).connect() as conn:
            q = lambda s: conn.execute(sa.text(s))  # noqa: E731
            assert q("SELECT version_num FROM alembic_version").scalar() == HEAD
            assert q("SELECT count(*) FROM schema_versions WHERE version = 'v24_job_runtime_indexes'").scalar() == 1
            # data survived
            assert q("SELECT count(*) FROM users").scalar() == 2
            assert q("SELECT count(*) FROM jobs").scalar() == 1
            assert q("SELECT disk_size_bytes FROM jobs WHERE id = 'j1'").scalar() == 5000000000
            assert q("SELECT filename FROM dataset_files WHERE id = 'f1'").scalar() == "X.tsv"
            # existing accounts are verified and NULLs were filled before NOT NULL
            assert q("SELECT bool_and(email_verified) FROM users").scalar() is True
            assert q("SELECT is_admin FROM users WHERE id = 'u2'").scalar() is False
            assert q("SELECT description FROM projects WHERE id = 'p1'").scalar() == ""
            assert q("SELECT archived FROM datasets WHERE id = 'd1'").scalar() is False
            # duplicates removed, most permissive share kept
            assert q("SELECT count(*) FROM project_datasets").scalar() == 1
            assert q("SELECT role FROM project_shares").scalars().all() == ["editor"]

    def test_upgrade_is_idempotent(self, pg_database, tmp_path):
        url, _ = pg_database
        _ok(_migrate(url, tmp_path=tmp_path))
        again = _ok(_migrate(url, tmp_path=tmp_path))
        assert HEAD in again.stdout

    def test_plain_alembic_refuses_a_legacy_database(self, pg_database, tmp_path):
        url, sync_url = pg_database
        _load_legacy(sync_url)
        env = {**os.environ, "PREDOMICS_DATABASE_URL": url, "PREDOMICS_DATA_DIR": str(tmp_path / "d")}
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(BACKEND / "alembic.ini"), "upgrade", "head"],
            cwd=BACKEND.parent, env=env, capture_output=True, text=True, timeout=120,
        )
        assert result.returncode != 0
        assert "python -m backend.app.migrate" in result.stderr
        with sa.create_engine(sync_url).connect() as conn:
            assert "alembic_version" not in sa.inspect(conn).get_table_names()

    def test_failed_adoption_leaves_the_database_untouched(self, pg_database, tmp_path):
        """Adoption is one transaction: a failure must not leave a half-migrated schema."""
        url, sync_url = pg_database
        _load_legacy(sync_url)
        engine = sa.create_engine(sync_url, poolclass=sa.pool.NullPool)
        with engine.begin() as conn:
            # Make the last legacy migration fail when it records itself.
            conn.execute(sa.text(
                "CREATE FUNCTION refuse_v24() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
                "IF NEW.version = 'v24_job_runtime_indexes' THEN RAISE EXCEPTION 'simulated failure'; END IF; "
                "RETURN NEW; END $$"
            ))
            conn.execute(sa.text(
                "CREATE TRIGGER refuse_v24 BEFORE INSERT ON schema_versions "
                "FOR EACH ROW EXECUTE FUNCTION refuse_v24()"
            ))
        result = _migrate(url, tmp_path=tmp_path)
        assert result.returncode != 0
        with engine.connect() as conn:
            assert "alembic_version" not in sa.inspect(conn).get_table_names()
            columns = {c["name"] for c in sa.inspect(conn).get_columns("jobs")}
            assert "started_at" not in columns  # rolled back with everything else
            conn.execute(sa.text("DROP TRIGGER refuse_v24 ON schema_versions"))
            conn.commit()
        # once the obstacle is gone the same command succeeds
        _ok(_migrate(url, tmp_path=tmp_path))
        engine.dispose()

    def test_downgrade_and_upgrade_again(self, pg_database, tmp_path):
        url, sync_url = pg_database
        _ok(_migrate(url, tmp_path=tmp_path))
        env = {**os.environ, "PREDOMICS_DATABASE_URL": url, "PREDOMICS_DATA_DIR": str(tmp_path / "d")}
        down = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(BACKEND / "alembic.ini"), "downgrade", "0001_baseline"],
            cwd=BACKEND.parent, env=env, capture_output=True, text=True, timeout=120,
        )
        assert down.returncode == 0, down.stderr[-2000:]
        _ok(_migrate(url, tmp_path=tmp_path))
        assert _migrate(url, "check", tmp_path=tmp_path).returncode == 0
