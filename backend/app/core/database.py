"""Async SQLAlchemy database setup."""

import os

from sqlalchemy import create_engine as create_sync_engine, event
from sqlalchemy.pool import NullPool
from starlette.requests import HTTPConnection
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


_is_sqlite = "sqlite" in settings.database_url
_sqlite_connect_args = {"timeout": 30, "check_same_thread": False} if _is_sqlite else {}


def _sqlite_wal_pragma(dbapi_conn, connection_record):
    """Enable WAL mode for SQLite concurrent access."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


# PREDOMICS_DB_NULLPOOL=1 opens a new connection per use instead of pooling. The
# test suite needs it on PostgreSQL: asyncpg connections belong to the event loop
# that created them, and every test runs in its own loop.
_pool_args = {"poolclass": NullPool} if os.environ.get("PREDOMICS_DB_NULLPOOL") == "1" and not _is_sqlite else {}

# Async engine — used by FastAPI request handlers
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args=_sqlite_connect_args if _is_sqlite else {},
    **_pool_args,
)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

# Sync engine — used by background tasks (which run in thread pools)
_sync_url = settings.database_url.replace("+asyncpg", "").replace("+aiosqlite", "")
sync_engine = create_sync_engine(
    _sync_url,
    echo=settings.debug,
    connect_args=_sqlite_connect_args if _is_sqlite else {},
    **_pool_args,
)
sync_session_factory = sessionmaker(sync_engine, expire_on_commit=False)

# Enable WAL mode for SQLite to allow concurrent reads/writes
if _is_sqlite:
    event.listen(sync_engine, "connect", _sqlite_wal_pragma)
    event.listen(engine.sync_engine, "connect", _sqlite_wal_pragma)


async def get_db(connection: HTTPConnection = None):
    """FastAPI dependency that yields a database session.

    The session is committed when the request ends. FastAPI runs the code after
    ``yield`` only once the response has been sent, which is too late on its own:
    a client that fires its next request as soon as it gets the answer could
    arrive before the commit and not see what it just created (a 404 on a project
    it had just been given, a 401 right after registering). The session is
    therefore also published on ``request.state`` so that
    :class:`CommitBeforeResponseMiddleware` can commit it *before* the response leaves.
    """
    async with async_session_factory() as session:
        if connection is not None:
            connection.state.db_session = session
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            if connection is not None and getattr(connection.state, "db_session", None) is session:
                connection.state.db_session = None


class CommitBeforeResponseMiddleware:
    """Commit the request's session just before its response starts to be sent.

    A plain ASGI middleware that must be the innermost one (added first): it
    wraps ``send``, so the commit runs in the endpoint's own task, after the
    handler has returned and before the first byte leaves — never concurrently
    with the handler or with the dependency's own clean-up.

    Only successful responses (status < 400) are committed here. Error responses
    keep the previous behaviour: ``get_db`` rolls back when the handler raised. If
    the commit itself fails, the exception surfaces as a normal 500 instead of a
    success answer for work that was not saved.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        state = scope.setdefault("state", {})

        async def send_committed(message):
            if message["type"] == "http.response.start" and message.get("status", 500) < 400:
                session = state.get("db_session")
                if session is not None and session.in_transaction():
                    await session.commit()
            await send(message)

        await self.app(scope, receive, send_committed)
