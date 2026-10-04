"""Fixtures of the retrieval tests: the fixture scripture store, in a session or behind a factory."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.retrieval.support import store_world


@pytest_asyncio.fixture
async def world(db_session: AsyncSession) -> AsyncSession:
    """A rolled-back session holding the fixture verses, hadiths, annotations and signals."""
    await store_world(db_session)
    return db_session


@pytest_asyncio.fixture
async def world_maker(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """
    A session factory over the fixture store, for code that opens and commits its own sessions.

    Every session joins one outer transaction through a savepoint, so a commit ends
    the savepoint and the test still rolls everything back.
    """
    connection = await engine.connect()
    transaction = await connection.begin()
    maker = async_sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    try:
        async with maker() as session, session.begin():
            await store_world(session)
        yield maker
    finally:
        await transaction.rollback()
        await connection.close()
