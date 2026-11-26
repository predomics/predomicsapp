"""Pytest conftest — set env overrides before any test module imports `app`.

This file is collected before any sibling `test_*.py`, so env vars set here
are guaranteed to be in place when `Settings()` is first instantiated (which
happens the first time `app.core.config` is imported — from either test_api.py
or test_services_unit.py).

Putting the same env setup at the top of test_api.py is not reliable: pytest
may collect test_services_unit.py first, which imports `app.services.*` and
therefore `app.core.config.settings`, baking in the default paths before
test_api.py's module-level code ever runs.
"""

from __future__ import annotations

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="predomics-test-")
os.environ["PREDOMICS_DATA_DIR"] = _tmp
os.environ["PREDOMICS_PROJECT_DIR"] = os.path.join(_tmp, "projects")
os.environ["PREDOMICS_UPLOAD_DIR"] = os.path.join(_tmp, "uploads")
os.environ["PREDOMICS_SAMPLES_DIR"] = os.path.join(_tmp, "samples")
os.environ["PREDOMICS_SAMPLE_DIR"] = os.path.join(_tmp, "samples")  # legacy compat
os.environ["PREDOMICS_DATABASE_URL"] = f"sqlite+aiosqlite:///{os.path.join(_tmp, 'test.db')}"

# Optional: run the whole suite on PostgreSQL instead of SQLite.
#   PREDOMICS_TEST_PG_URL=postgresql+asyncpg://user:pass@host:5432/dbname pytest tests/
# The tests create and drop every table around each test, so they never run in the
# database named in the URL: a scratch database is created next to it and dropped
# at the end of the session. The user therefore needs the CREATEDB privilege.
_PG_URL = os.environ.get("PREDOMICS_TEST_PG_URL", "")
_pg_scratch = None
if _PG_URL:
    import sqlalchemy as _sa

    _base = _sa.engine.make_url(_PG_URL)
    _admin_url = _base.set(drivername="postgresql+psycopg2")
    _pg_scratch = f"predomics_test_{os.getpid()}_{os.urandom(3).hex()}"
    _admin = _sa.create_engine(_admin_url, isolation_level="AUTOCOMMIT", poolclass=_sa.pool.NullPool)
    with _admin.connect() as _conn:
        _conn.execute(_sa.text(f'CREATE DATABASE "{_pg_scratch}"'))
    _admin.dispose()
    os.environ["PREDOMICS_DB_NULLPOOL"] = "1"   # one event loop per test: no pooled asyncpg connections
    os.environ["PREDOMICS_DATABASE_URL"] = _base.set(
        drivername="postgresql+asyncpg", database=_pg_scratch
    ).render_as_string(hide_password=False)
os.environ["PREDOMICS_SECRET_KEY"] = "test-secret-key"
os.environ["PREDOMICS_RATE_LIMIT_ENABLED"] = "false"
# Existing tests register with very short passwords.
os.environ["PREDOMICS_PASSWORD_MIN_LENGTH"] = "1"
# CI has no gpredomicspy wheel: allow the labelled mock engine there.
os.environ["PREDOMICS_ALLOW_MOCK_ENGINE"] = "true"
# Run analysis jobs inside the request's background tasks (deterministic tests)
# instead of the bounded job-runner thread pool.
os.environ["PREDOMICS_JOBS_INLINE"] = "1"

# Expose the tmpdir for tests that want to write fixture files under it.
os.environ["PREDOMICS_TEST_TMPDIR"] = _tmp



def pytest_sessionfinish(session, exitstatus):
    """Drop the PostgreSQL scratch database created above."""
    if not _pg_scratch:
        return
    import sqlalchemy as sa

    try:
        from app.core.database import sync_engine

        sync_engine.dispose()
    except Exception:  # noqa: BLE001
        pass
    admin = sa.create_engine(
        sa.engine.make_url(_PG_URL).set(drivername="postgresql+psycopg2"),
        isolation_level="AUTOCOMMIT", poolclass=sa.pool.NullPool,
    )
    with admin.connect() as conn:
        conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{_pg_scratch}" WITH (FORCE)'))
    admin.dispose()
