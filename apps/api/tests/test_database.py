from __future__ import annotations

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src import database
from src.config import get_settings
from src.models import GeoName


def test_the_engine_is_cached_and_built_without_connecting():
    engine = database.get_engine()

    assert isinstance(engine, AsyncEngine)
    assert database.get_engine() is engine
    assert engine.url.drivername == "postgresql+asyncpg"
    assert engine.url.host == "127.0.0.1"


def test_the_engine_is_configured_with_a_short_timeout_and_the_search_path(monkeypatch):
    captured: dict = {}

    def fake_create(url, **kwargs):
        captured.update(kwargs, url=url)
        return "engine"

    monkeypatch.setattr(database, "create_async_engine", fake_create)
    settings = get_settings()

    # __wrapped__ builds a fresh engine without touching the cached one.
    assert database.get_engine.__wrapped__() == "engine"

    assert captured["url"] == settings.database_url.get_secret_value()
    assert captured["pool_size"] == settings.db_pool_size
    assert captured["max_overflow"] == settings.db_max_overflow
    assert captured["pool_timeout"] == settings.db_connect_timeout
    assert captured["pool_pre_ping"] is True
    assert captured["hide_parameters"] is True
    assert captured["connect_args"] == {
        "timeout": settings.db_connect_timeout,
        "server_settings": {"search_path": "app,geodata,public"},
    }
    assert settings.db_connect_timeout <= 5


def test_the_session_factory_is_bound_to_the_engine_and_keeps_objects_after_commit():
    sessionmaker = database.get_sessionmaker()

    assert database.get_sessionmaker() is sessionmaker
    assert sessionmaker.kw["bind"] is database.get_engine()
    assert sessionmaker.kw["expire_on_commit"] is False


async def test_get_db_yields_a_working_session_with_the_search_path_set(engine):
    sessions = []
    async for session in database.get_db():
        sessions.append(session)
        assert isinstance(session, AsyncSession)
        search_path = (await session.execute(text("SHOW search_path"))).scalar_one()
        assert (await session.execute(text("SELECT 1"))).scalar_one() == 1

    assert search_path == "app,geodata,public"
    assert sessions[0].in_transaction() is False


async def test_get_db_rolls_back_what_the_request_did_not_commit(engine):
    async for session in database.get_db():
        session.add(GeoName(geoname_id=987654, name="Uncommitted"))
        await session.flush()

    async for session in database.get_db():
        left = (await session.execute(select(func.count()).select_from(GeoName))).scalar_one()

    assert left == 0


async def test_dispose_engine_closes_the_pool_and_the_engine_keeps_working(engine):
    async for session in database.get_db():
        await session.execute(text("SELECT 1"))
    assert database.get_engine().pool.checkedout() == 0

    await database.dispose_engine()

    async for session in database.get_db():
        assert (await session.execute(text("SELECT 1"))).scalar_one() == 1


async def test_a_database_error_does_not_carry_the_values_of_the_statement(engine):
    from sqlalchemy.exc import IntegrityError

    async for session in database.get_db():
        session.add(GeoName(geoname_id=1, name="First"))
        await session.flush()
        with pytest.raises(IntegrityError) as caught:
            async with session.begin_nested():
                session.add(GeoName(geoname_id=1, name="private-answer-muslim"))
                await session.flush()

    assert "private-answer-muslim" not in str(caught.value)
    assert "parameters hidden" in str(caught.value)
