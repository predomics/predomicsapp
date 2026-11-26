"""Database schema upgrades.

    python -m backend.app.migrate            upgrade to the latest revision
    python -m backend.app.migrate status     print where the database is
    python -m backend.app.migrate check      exit 1 if the schema differs from the models

The application calls :func:`upgrade_database` at startup unless
``PREDOMICS_AUTO_MIGRATE=false``; then it only verifies (:func:`require_up_to_date`)
and this module is run as a separate deployment step.

What an upgrade does depends on what it finds:

* **empty database** — ``alembic upgrade head`` creates everything;
* **Alembic-managed database** — pending revisions are applied;
* **database created before Alembic** (application tables, no ``alembic_version``)
  — in one transaction: missing tables are created at the baseline shape, the
  frozen legacy migrations (``migrations_legacy.py``) bring the rest to the
  "v24" state, and the baseline revision is stamped; then pending revisions are
  applied as usual. If anything fails the transaction rolls back and the
  database is left exactly as it was.

On PostgreSQL the whole upgrade runs under an advisory lock, so several
processes starting together do not race.

SQLite is supported for development and tests only: a new SQLite database is
created directly from the models and stamped at the latest revision.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import text

from .core.config import settings
from .core.database import Base, engine
from .models import db_models  # noqa: F401 — registers the tables on Base.metadata

_log = logging.getLogger(__name__)

BASELINE_REVISION = "0001_baseline"
_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
# Arbitrary constant identifying this application's migrations for pg_advisory_lock.
_MIGRATION_LOCK_ID = 7360421


def auto_migrate_enabled() -> bool:
    """PREDOMICS_AUTO_MIGRATE (default true)."""
    value = getattr(settings, "auto_migrate", None)
    if value is None:
        value = os.environ.get("PREDOMICS_AUTO_MIGRATE", "true")
    return str(value).strip().lower() not in ("0", "false", "no", "off")


# ---------------------------------------------------------------------------
# Alembic plumbing (synchronous; called through AsyncConnection.run_sync)
# ---------------------------------------------------------------------------

def _config(connection, **attributes):
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_INI))
    cfg.attributes["connection"] = connection
    cfg.attributes["target_metadata"] = Base.metadata
    cfg.attributes.update(attributes)
    return cfg


def _head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(Config(str(_ALEMBIC_INI))).get_current_head()


def _current(connection) -> str | None:
    from alembic.migration import MigrationContext

    return MigrationContext.configure(connection).get_current_revision()


def _state(connection) -> tuple[str, str | None]:
    """('empty' | 'legacy' | 'alembic', current revision)."""
    tables = set(sa.inspect(connection).get_table_names())
    if "alembic_version" in tables:
        revision = _current(connection)
        if revision is not None:
            return "alembic", revision
    if tables & set(Base.metadata.tables):
        return "legacy", None
    return "empty", None


def _upgrade(connection, target: str = "head", **attributes) -> None:
    from alembic import command

    command.upgrade(_config(connection, **attributes), target)


def _stamp(connection, target: str = "head") -> None:
    from alembic import command

    command.stamp(_config(connection), target)


def schema_differences(connection) -> list:
    """Differences between the live schema and the models ([] when identical)."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    ctx = MigrationContext.configure(connection, opts={"compare_type": True})
    return compare_metadata(ctx, Base.metadata)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def _adopt_legacy_database() -> None:
    """Bring a pre-Alembic PostgreSQL database to the baseline, atomically."""
    from .migrations_legacy import run_legacy_migrations

    _log.warning("Database predates Alembic: running the legacy migrations, then stamping %s",
                 BASELINE_REVISION)
    async with engine.begin() as conn:
        # Creates the tables the old database lacks and records the baseline revision.
        await conn.run_sync(_upgrade, BASELINE_REVISION, adopting_legacy=True)
        await run_legacy_migrations(conn)
    _log.info("Legacy database adopted at revision %s", BASELINE_REVISION)


async def upgrade_database() -> str:
    """Upgrade the database to the latest revision; returns that revision."""
    is_pg = engine.dialect.name == "postgresql"
    head = _head()
    async with engine.connect() as lock_conn:
        if is_pg:
            await lock_conn.execute(text("SELECT pg_advisory_lock(:id)"), {"id": _MIGRATION_LOCK_ID})
        try:
            async with engine.connect() as conn:
                state, revision = await conn.run_sync(_state)

            if not is_pg:
                # Development databases: build from the models, no history to replay.
                if state != "alembic":
                    async with engine.begin() as conn:
                        await conn.run_sync(Base.metadata.create_all)
                        await conn.run_sync(_stamp, "head")
                    _log.info("Created the %s database from the models (revision %s)",
                              engine.dialect.name, head)
                    return head
            elif state == "legacy":
                await _adopt_legacy_database()
                revision = BASELINE_REVISION

            if revision != head:
                _log.info("Upgrading database schema: %s -> %s", revision or "(empty)", head)
                async with engine.begin() as conn:
                    await conn.run_sync(_upgrade, "head")
            else:
                _log.info("Database schema is up to date (%s)", head)
            return head
        finally:
            if is_pg:
                await lock_conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": _MIGRATION_LOCK_ID})


async def status() -> dict:
    """{'state', 'revision', 'head', 'up_to_date'} for the configured database."""
    head = _head()
    async with engine.connect() as conn:
        state, revision = await conn.run_sync(_state)
    return {"state": state, "revision": revision, "head": head, "up_to_date": revision == head}


async def require_up_to_date() -> None:
    """Raise if the schema is not at the latest revision (PREDOMICS_AUTO_MIGRATE=false)."""
    info = await status()
    if not info["up_to_date"]:
        raise RuntimeError(
            f"Database schema is at {info['revision'] or info['state']} but this version needs "
            f"{info['head']}. Run `python -m backend.app.migrate` (PREDOMICS_AUTO_MIGRATE is off)."
        )


async def _main(argv: list[str]) -> int:
    command = argv[0] if argv else "upgrade"
    if command == "upgrade":
        print(f"Database is at revision {await upgrade_database()}")
        return 0
    if command == "status":
        info = await status()
        print(f"state={info['state']} revision={info['revision']} head={info['head']} "
              f"up_to_date={info['up_to_date']}")
        return 0 if info["up_to_date"] else 1
    if command == "check":
        async with engine.connect() as conn:
            differences = await conn.run_sync(schema_differences)
        for difference in differences:
            print(difference)
        print("Schema matches the models." if not differences
              else f"{len(differences)} difference(s) between the schema and the models.")
        return 1 if differences else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.exit(asyncio.run(_main(sys.argv[1:])))
