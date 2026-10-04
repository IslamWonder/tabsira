"""Fixtures of the insight engine tests: the whole fixture store, in a session or behind a factory."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.insight.support import store_engine_world


@pytest_asyncio.fixture
async def store(db_session: AsyncSession) -> AsyncSession:
    """A rolled-back session holding the scripture fixtures, the ontology and the path."""
    await store_engine_world(db_session)
    return db_session


@pytest_asyncio.fixture
async def maker(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """The same store behind a factory whose commits are savepoints of one outer transaction."""
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    try:
        async with factory() as session, session.begin():
            await store_engine_world(session)
        yield factory
    finally:
        await transaction.rollback()
        await connection.close()
