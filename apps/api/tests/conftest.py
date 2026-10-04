"""
Pytest fixtures: hermetic settings, the test database and an HTTP client.

Strategy:
- The suite decides its own configuration. A developer's .env is never read,
  and every environment variable that a setting maps to is removed first, so a
  key in the shell or in CI cannot change what a test sees.
- Database tests run against the `tabsira_test` database named by
  TEST_DATABASE_URL (in the root .env, written by scripts/setup-db.sh). It
  must end in `_test`; the suite refuses to run against anything else.
- Each test gets its own session in a transaction that is rolled back.
- With pytest-xdist every worker gets its own database, copied from the
  server-wide `tabsira_template` database (TEST_TEMPLATE_DATABASE) that
  scripts/setup-db.sh provisions with both schemas and every extension but no
  tables; the worker then builds the tables in its copy. The test role is not a
  superuser, so it could not create PostGIS or TimescaleDB itself, and the suite
  makes no template of its own: TimescaleDB attaches a background session to
  every database that accepts connections, within seconds, and PostgreSQL
  refuses to copy a database somebody is connected to.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

# These must be set before `src.config` is imported: the .env lookup is fixed
# when the Settings class is defined.
os.environ["TABSIRA_ENV_FILE"] = ""

import asyncpg
import pytest
import pytest_asyncio
from dotenv import dotenv_values
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.config import Settings
from tests.helpers import client_for

REPO_ROOT = Path(__file__).resolve().parents[3]

SEARCH_PATH = "app,geodata,public"
# Provisioned by scripts/setup-db.sh: both schemas and every extension, no tables.
DEFAULT_BASE_TEMPLATE = "tabsira_template"
# A fixed key: workers take the same advisory lock around copying the template.
TEMPLATE_LOCK_KEY = 7_424_011


def _configured_test_url() -> str | None:
    """Return TEST_DATABASE_URL from the environment or from the root .env, if set."""
    return (
        os.environ.get("TEST_DATABASE_URL")
        or dotenv_values(REPO_ROOT / ".env").get("TEST_DATABASE_URL")
        or None
    )


def _configured_base_template() -> str:
    """Return the database the test template is copied from: TEST_TEMPLATE_DATABASE or the default."""
    return (
        os.environ.get("TEST_TEMPLATE_DATABASE")
        or dotenv_values(REPO_ROOT / ".env").get("TEST_TEMPLATE_DATABASE")
        or DEFAULT_BASE_TEMPLATE
    )


def _scrub_environment() -> None:
    """Remove every variable a setting reads, so a test sees only what it sets."""
    keys = {name.upper() for name in Settings.model_fields}
    for key in list(os.environ):
        upper = key.upper()
        if upper in keys or upper.startswith(("AI_OVH__", "AI_OPENAI__")):
            del os.environ[key]


_BASE_URL = _configured_test_url()
_BASE_TEMPLATE = _configured_base_template()
# When no URL is configured the suite still has to import: the settings need a
# database URL. Database tests then fail with a clear message instead.
_PLACEHOLDER_URL = "postgresql+asyncpg://tabsira:unset@127.0.0.1:5432/tabsira_test"
_TEST_URL = make_url(_BASE_URL or _PLACEHOLDER_URL)

if not (_TEST_URL.database or "").endswith("_test"):
    message = f"TEST_DATABASE_URL must name a database ending in _test, not {_TEST_URL.database!r}"
    raise RuntimeError(message)

_XDIST_WORKER = os.environ.get("PYTEST_XDIST_WORKER")
_BASE_DATABASE = _TEST_URL.database or ""
_WORKER_URL: URL = (
    _TEST_URL.set(database=f"{_BASE_DATABASE}_{_XDIST_WORKER}") if _XDIST_WORKER else _TEST_URL
)

_scrub_environment()
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = _WORKER_URL.render_as_string(hide_password=False)

from src.database import dispose_engine  # noqa: E402
from src.main import create_app  # noqa: E402
from tests.dbschema import create_schema  # noqa: E402


def _dsn(url: URL) -> str:
    """Return the URL in the form asyncpg understands."""
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


async def _admin_connection() -> asyncpg.Connection:
    """Connect to the `postgres` database, for statements that cannot run inside the test one."""
    return await asyncpg.connect(_dsn(_TEST_URL.set(database="postgres")))


def _engine_for(url: URL) -> AsyncEngine:
    return create_async_engine(
        url,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": SEARCH_PATH}},
    )


async def _ensure_worker_database() -> None:
    """Give this xdist worker its own empty database, copied from the provisioned template."""
    if not _XDIST_WORKER:
        return

    admin = await _admin_connection()
    try:
        # One copy at a time: a copy is quick, and PostgreSQL is happier alone with it.
        await admin.execute("SELECT pg_advisory_lock($1)", TEMPLATE_LOCK_KEY)
        database = _WORKER_URL.database
        await admin.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
        # The test role cannot create PostGIS, pgvector or TimescaleDB, so the copy
        # starts from the provisioned database that already has them. Where there is
        # none (a CI role that may create extensions) the plain default template is
        # used and `create_schema` creates the extensions itself.
        provisioned = await admin.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", _BASE_TEMPLATE
        )
        source = f' TEMPLATE "{_BASE_TEMPLATE}"' if provisioned else ""
        await admin.execute(f'CREATE DATABASE "{database}"{source}')
        await admin.execute("SELECT pg_advisory_unlock($1)", TEMPLATE_LOCK_KEY)
    finally:
        await admin.close()


async def _drop_worker_database() -> None:
    if not _XDIST_WORKER:
        return
    admin = await _admin_connection()
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{_WORKER_URL.database}" WITH (FORCE)')
    finally:
        await admin.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _close_app_engine() -> AsyncIterator[None]:
    """Close the connections of the application's own engine when the session ends."""
    yield
    await dispose_engine()


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    """The engine of the test database, with the schema built."""
    if _BASE_URL is None:
        pytest.fail(
            "TEST_DATABASE_URL is not set. Run scripts/setup-db.sh, which creates the "
            "tabsira_test database and writes the URL into the root .env.",
            pytrace=False,
        )
    try:
        await _ensure_worker_database()
    except asyncpg.InsufficientPrivilegeError:
        pytest.fail(
            "Parallel runs (-n) give each worker its own database, and the test role may not "
            "create databases. Grant it CREATEDB on development and CI hosts (never in "
            "production), or run the suite serially.",
            pytrace=False,
        )
    engine = _engine_for(_WORKER_URL)
    async with engine.begin() as connection:
        await create_schema(connection)
    try:
        yield engine
    finally:
        await engine.dispose()
        await _drop_worker_database()


@pytest_asyncio.fixture
async def db_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that is rolled back when the test ends."""
    connection = await engine.connect()
    transaction = await connection.begin()
    session = async_sessionmaker(bind=connection, expire_on_commit=False)()
    try:
        yield session
    finally:
        await session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()


@pytest.fixture(scope="session")
def app() -> FastAPI:
    """The application, built from the suite's hermetic settings."""
    return create_app()


@pytest.fixture
def make_settings() -> Callable[..., Settings]:
    """Build Settings for a test: no .env, the suite's environment plus the given values."""

    def build(**values: Any) -> Settings:
        return Settings(_env_file=None, **values)

    return build


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """A client of the suite's application."""
    async with client_for(app) as http:
        yield http
