"""Async engine and session factory, configured per database backend."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

if TYPE_CHECKING:
    from app.config import Settings


def make_engine(settings: Settings) -> AsyncEngine:
    """Create an AsyncEngine for the configured backend.

    SQLite (especially ``:memory:``) uses a single shared connection so the
    database persists across the session pool; Postgres/MySQL use the configured
    connection pool size.
    """
    url = settings.database_url()
    kwargs: dict[str, Any] = {"echo": settings.database.echo}
    if settings.database.type == "sqlite":
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_size"] = settings.database.pool_size
        kwargs["pool_pre_ping"] = True
    return create_async_engine(url, **kwargs)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield a session, committing on success and rolling back on error."""
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
