"""Async database engine and session dependency."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import get_settings

# Every connection sees the application schema first, then the geodata
# reference schema, then public (where the PostgreSQL extensions live).
SEARCH_PATH = "app,geodata,public"


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """
    Build the process-wide engine on first use.

    The engine connects lazily, so building it never touches the network. The
    connect timeout is short: a database that is down must fail a request, not
    hang it.
    """
    settings = get_settings()
    return create_async_engine(
        settings.database_url.get_secret_value(),
        echo=False,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_connect_timeout,
        connect_args={
            "timeout": settings.db_connect_timeout,
            "server_settings": {"search_path": SEARCH_PATH},
        },
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the session factory bound to the engine."""
    return async_sessionmaker(bind=get_engine(), expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    """
    Yield a session for one request.

    Closing the session at the end of the request releases its connection and
    rolls back anything that was not committed.
    """
    async with get_sessionmaker()() as session:
        yield session


async def dispose_engine() -> None:
    """Close every pooled connection; called when the application shuts down."""
    await get_engine().dispose()
