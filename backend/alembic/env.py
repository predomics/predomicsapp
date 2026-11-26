"""Alembic environment.

Two ways in:

* from the application (``app/migrate.py``): the caller passes an open
  connection and the target metadata through ``config.attributes``; nothing is
  imported from the application here;
* from the ``alembic`` command line: the URL comes from the application
  settings (``PREDOMICS_DATABASE_URL``) and the models are imported.
"""

import sys
from pathlib import Path

import sqlalchemy as sa
from alembic import context

config = context.config


def _import_app():
    """Import (database_url, Base.metadata) for command-line use."""
    root = str(Path(__file__).resolve().parents[2])  # directory that contains "backend/"
    if root not in sys.path:
        sys.path.insert(0, root)
    from backend.app.core.config import settings
    from backend.app.core.database import Base
    from backend.app.models import db_models  # noqa: F401 — registers the tables

    url = settings.database_url.replace("+asyncpg", "").replace("+aiosqlite", "")
    return url, Base.metadata


def _configure(connection, target_metadata):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        # SQLite cannot ALTER most things in place; batch mode recreates the table.
        render_as_batch=connection.dialect.name == "sqlite",
    )


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        # The caller owns the transaction (and commits or rolls back).
        _configure(connection, config.attributes.get("target_metadata"))
        with context.begin_transaction():
            context.run_migrations()
        return

    url, metadata = _import_app()
    engine = sa.create_engine(url, poolclass=sa.pool.NullPool)
    with engine.connect() as connection:
        _configure(connection, metadata)
        with context.begin_transaction():
            context.run_migrations()


def run_migrations_offline() -> None:
    url, metadata = _import_app()
    context.configure(url=url, target_metadata=metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
