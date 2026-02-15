"""Async SQLAlchemy database setup."""

from sqlalchemy import create_engine as create_sync_engine, event
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


# Async engine — used by FastAPI request handlers
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args=_sqlite_connect_args if _is_sqlite else {},
)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

# Sync engine — used by background tasks (which run in thread pools)
_sync_url = settings.database_url.replace("+asyncpg", "").replace("+aiosqlite", "")
sync_engine = create_sync_engine(
    _sync_url,
    echo=settings.debug,
    connect_args=_sqlite_connect_args if _is_sqlite else {},
)
sync_session_factory = sessionmaker(sync_engine, expire_on_commit=False)

# Enable WAL mode for SQLite to allow concurrent reads/writes
if _is_sqlite:
    event.listen(sync_engine, "connect", _sqlite_wal_pragma)
    event.listen(engine.sync_engine, "connect", _sqlite_wal_pragma)


async def get_db():
    """FastAPI dependency that yields a database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
