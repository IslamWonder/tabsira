"""Fixtures of the scripture tests: sessions that commit into a rolled-back transaction."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.scripture.fixtures import store_quran


@pytest_asyncio.fixture
async def scripture_maker(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """
    A session factory for code that commits, such as the commands.

    Every session joins one outer transaction through a savepoint, so a commit
    ends the savepoint and the test still rolls everything back.
    """
    connection = await engine.connect()
    transaction = await connection.begin()
    try:
        yield async_sessionmaker(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
    finally:
        await transaction.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def quran_session(db_session: AsyncSession) -> AsyncSession:
    """A session holding the fixture verses of quranpedia mushaf 2, imported as the importer does."""
    await store_quran(db_session)
    return db_session
