from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.database import get_db
from src.main import create_app
from tests.helpers import client_for


def failing_session(error: BaseException) -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = error
    return session


@pytest.fixture
def app_with_session(make_settings):
    """Build an application whose database session is the one the test provides."""

    def build(session, **settings):
        application = create_app(make_settings(**settings))

        async def override():
            yield session

        application.dependency_overrides[get_db] = override
        return application

    return build


async def test_liveness_answers_ok(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_liveness_does_not_touch_the_database(app_with_session):
    session = failing_session(OSError("database is down"))

    async with client_for(app_with_session(session)) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    session.execute.assert_not_called()


async def test_readiness_is_ok_when_the_database_answers(engine, client):
    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok"}}


async def test_readiness_reports_degraded_when_the_database_fails(app_with_session, caplog):
    session = failing_session(ConnectionRefusedError("password=hunter2"))

    with caplog.at_level(logging.WARNING, logger="tabsira.health"):
        async with client_for(app_with_session(session)) as client:
            response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "checks": {"database": "down"}}
    assert "hunter2" not in response.text
    # The log names the kind of failure, not its text, which may carry a DSN.
    assert "ConnectionRefusedError" in caplog.text
    assert "hunter2" not in caplog.text


async def test_readiness_does_not_hang_when_the_database_does(app_with_session):
    import asyncio

    async def hang(*_args, **_kwargs):
        await asyncio.sleep(30)

    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = hang

    async with client_for(app_with_session(session, db_connect_timeout=0.05)) as client:
        response = await asyncio.wait_for(client.get("/health/ready"), timeout=5)

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


async def test_readiness_is_degraded_for_an_engine_nobody_listens_on(app_with_session):
    # Port 1 on the loopback interface refuses at once: a real connection
    # failure, with no network involved.
    dead = create_async_engine(
        "postgresql+asyncpg://tabsira:pw@127.0.0.1:1/tabsira", connect_args={"timeout": 1}
    )
    session = AsyncSession(bind=dead)
    try:
        async with client_for(app_with_session(session, db_connect_timeout=1.0)) as client:
            response = await client.get("/health/ready")
    finally:
        await session.close()
        await dead.dispose()

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "checks": {"database": "down"}}
