"""
Fixtures of the scan workflow tests.

Everything runs on one database connection inside a transaction that is rolled
back: the application's requests, the job and the test all open their own
sessions, whose commits are savepoints of that transaction, so they see each
other's writes as the real processes do. Redis is an in-process fake, the
queue records what it is asked, and no model, detector or address is reached.
"""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from fastapi import FastAPI
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.config import Settings
from src.database import get_db
from src.main import create_app
from src.models import Hadith, HadithClassification, QuranSurah, QuranVerse, User
from src.schemas.learning_path import LearningPathFile
from src.scripture.guard import WritePurpose, allow_scripture_writes
from src.scripture.rulings import RulingInput, find_hadith, record_ruling
from src.services.masar_import import import_path
from tests.conftest import browser_for
from tests.fakes import FakeModelClient
from tests.scripture.fixtures import store_hadiths, store_quran

DATA = Path(__file__).resolve().parent / "data"
REPO_ROOT = Path(__file__).resolve().parents[4]
MASAR = REPO_ROOT / "data" / "masar" / "tabsira-masar-1.0.json"


def photo(width: int = 96, height: int = 64, fmt: str = "JPEG") -> bytes:
    """A small real photo, made here so no file from elsewhere is needed."""
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (40, 120, 60)).save(buffer, format=fmt)
    return buffer.getvalue()


async def store_extra(session: AsyncSession) -> None:
    """Import the extra verses and hadith the tutorial and the treasures cite."""
    extra = json.loads((DATA / "extra-scripture.json").read_text(encoding="utf-8"))
    await allow_scripture_writes(session, WritePurpose.IMPORT)
    for surah in extra["surahs"]:
        session.add(QuranSurah(**surah))
    await session.flush()
    for verse in extra["verses"]:
        session.add(QuranVerse(**verse))
    for hadith in extra["hadiths"]:
        session.add(Hadith(**hadith))
    await session.flush()


async def store_path(session: AsyncSession) -> None:
    raw = MASAR.read_bytes()
    await import_path(
        session,
        LearningPathFile.model_validate_json(raw),
        source_file=str(MASAR),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        activate=True,
    )


async def rule(
    session: AsyncSession,
    collection: str,
    number: str,
    classification: HadithClassification = HadithClassification.SAHIH,
) -> None:
    """Record an editor's dorar.net ruling, as the command does."""
    hadith = await find_hadith(session, collection, number)
    assert hadith is not None
    await record_ruling(
        session,
        hadith.id,
        RulingInput(
            ruling_text="صحيح",
            scholar="البخاري",
            source_book="صحيح البخاري",
            page="1",
            dorar_url="https://dorar.net/h/test",
            classification=classification,
            editor_name="محرر الاختبار",
        ),
    )


@pytest_asyncio.fixture
async def maker(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Sessions on one connection whose commits are savepoints of a rolled-back transaction."""
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
async def store(maker: async_sessionmaker[AsyncSession]) -> async_sessionmaker[AsyncSession]:
    """The fixture verses and hadith, the extra ones, and the real learning path."""
    async with maker() as session:
        await store_quran(session)
        await store_hadiths(session)
        await store_extra(session)
        await store_path(session)
        await session.commit()
    return maker


@pytest_asyncio.fixture
async def redis() -> AsyncIterator[FakeAsyncRedis]:
    client = FakeAsyncRedis()
    try:
        yield client
    finally:
        await client.flushall()
        await client.aclose()


class FakeQueue:
    """Records the runs it is asked for; `broken` makes it refuse."""

    def __init__(self) -> None:
        self.runs: list[tuple[int, int]] = []
        self.broken = False

    async def enqueue(self, scan_id: int, run: int) -> None:
        from src.scans.queue import QueueUnavailableError

        if self.broken:
            message = "down"
            raise QueueUnavailableError(message)
        self.runs.append((scan_id, run))


@pytest.fixture
def queue() -> FakeQueue:
    return FakeQueue()


class FakeFetcher:
    """Answers photo addresses from a table; an exception in it is raised."""

    def __init__(self) -> None:
        self.answers: dict[str, bytes | Exception] = {}
        self.asked: list[str] = []

    async def __call__(self, url: str) -> bytes:
        self.asked.append(url)
        answer = self.answers[url]
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def fetcher() -> FakeFetcher:
    return FakeFetcher()


@pytest.fixture
def model() -> FakeModelClient:
    """The model the chat talks to; tests put answers in its queue."""
    return FakeModelClient()


@pytest.fixture
def flow_settings(make_settings: Callable[..., Settings]) -> Settings:
    return make_settings(password_bcrypt_rounds=4)


@pytest.fixture
def flow_app(
    flow_settings: Settings,
    maker: async_sessionmaker[AsyncSession],
    redis: FakeAsyncRedis,
    queue: FakeQueue,
    fetcher: FakeFetcher,
    model: FakeModelClient,
) -> FastAPI:
    application = create_app(flow_settings)

    async def session() -> AsyncIterator[AsyncSession]:
        async with maker() as db:
            yield db

    application.dependency_overrides[get_db] = session
    application.state.redis = redis
    application.state.scan_queue = queue
    application.state.image_fetcher = fetcher

    def client_factory(log: Any) -> FakeModelClient:
        model.log = log
        return model

    application.state.model_client_factory = client_factory
    return application


@pytest_asyncio.fixture
async def browser(flow_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """A browser on the web app's origin, with its own cookie jar (a guest at first)."""
    async with browser_for(flow_app) as http:
        yield http


@pytest_asyncio.fixture
async def other(flow_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """A second, unrelated browser."""
    async with browser_for(flow_app) as http:
        yield http


async def make_account(
    maker: async_sessionmaker[AsyncSession], email: str = "reader@example.com"
) -> User:
    from src import security
    from src.services import profile_service

    async with maker() as session:
        user = User(
            email=email,
            password_hash=security.hash_password("correct horse battery", 4),
            display_name="Reader",
        )
        session.add(user)
        await session.flush()
        await profile_service.ensure_profile(session, user.id)
        await session.commit()
    return user


async def as_guest(
    client: AsyncClient, maker: async_sessionmaker[AsyncSession], settings: Settings
) -> Any:
    """Make a guest and give its signed cookie to `client`; return its owner."""
    from src.owner import Owner
    from src.services import guest_service

    async with maker() as session:
        token, guest = await guest_service.create(session, settings)
        await session.commit()
    client.cookies.set(
        settings.guest_cookie_name,
        guest_service.cookie_value(settings, token),
        domain=settings.session_cookie_domain,
    )
    return Owner(guest_key=guest.key)


async def sign_in(client: AsyncClient, email: str = "reader@example.com") -> None:
    response = await client.post(
        "/auth/login", json={"email": email, "password": "correct horse battery"}
    )
    assert response.status_code == 200, response.text
