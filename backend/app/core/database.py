"""Async SQLAlchemy database setup."""

from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


# Async engine — used by FastAPI request handlers
engine = create_async_engine(settings.database_url, echo=settings.debug)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

# Sync engine — used by background tasks (which run in thread pools)
_sync_url = settings.database_url.replace("+asyncpg", "").replace("+aiosqlite", "")
sync_engine = create_sync_engine(_sync_url, echo=settings.debug)
sync_session_factory = sessionmaker(sync_engine, expire_on_commit=False)


async def get_db():
    """FastAPI dependency that yields a database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
