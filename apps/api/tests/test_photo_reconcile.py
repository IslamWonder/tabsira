"""
A public copy the store failed to delete is reconciled later, in one process (v2 §19).

The API asks the worker after a failure; the hourly command runs the same reconcile; neither
ever raises at the person, and two runs never overlap.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src import worker
from src.cli import reconcile_photos
from src.models import Insight, User
from src.owner import Owner
from src.services import photo_reconcile, photo_service
from src.services.photo_service import ReconcileReport
from src.storage.base import StorageUnavailableError, new_private_key, new_public_key
from src.storage.local import LocalStorage
from src.storage.photos import PhotoStore
from tests.scans.builders import insight_row, scan_row
from tests.support_images import jpeg_of, pixels


@pytest.fixture
def factory(db_session):
    return async_sessionmaker(bind=db_session.bind, expire_on_commit=False)


async def orphan_copy(db: AsyncSession, user: User, store: PhotoStore) -> Insight:
    """An insight with a public copy that nothing shows: the store failed its deletion."""
    owner = Owner(user_id=user.id)
    scan = scan_row(owner, status="done")
    db.add(scan)
    await db.flush()
    private, public = new_private_key(), new_public_key()
    for key in (private, public):
        await store.storage.put(key, jpeg_of(pixels()))
    insight = insight_row(owner, scan_id=scan.id, photo_key=private, photo_public_key=public)
    db.add(insight)
    await db.flush()
    return insight


async def public_key_of(db: AsyncSession, insight: Insight) -> str | None:
    return await db.scalar(select(Insight.photo_public_key).where(Insight.id == insight.id))


# ─── The request from the API to the worker ───


async def test_the_api_kicks_the_worker_s_reconcile_task(monkeypatch):
    kicked: list[bool] = []

    async def kiq() -> None:
        kicked.append(True)

    monkeypatch.setattr(worker.reconcile_photos_task, "kiq", kiq)

    await photo_reconcile.TaskiqRetryQueue().request()

    assert kicked == [True]


async def test_a_queue_that_is_down_is_logged_and_the_request_is_dropped(caplog):
    class Down:
        async def request(self) -> None:
            raise ConnectionError("refused")

    photo_reconcile.use_retry_queue(Down())
    with caplog.at_level(logging.WARNING, logger="tabsira.photos"):
        await photo_reconcile.request_retry()

    assert [record.getMessage() for record in caplog.records] == [
        (
            "public photo copies: the reconcile could not be queued (ConnectionError); "
            "the timer will run it"
        )
    ]


def test_without_a_queue_of_the_tests_the_worker_s_is_used_once():
    photo_reconcile.use_retry_queue(None)

    made = photo_reconcile.retry_queue()

    assert isinstance(made, photo_reconcile.TaskiqRetryQueue)
    assert photo_reconcile.retry_queue() is made


# ─── The worker's task ───


@dataclass
class Shared:
    sessionmaker: async_sessionmaker[AsyncSession]
    settings: object


async def test_the_task_waits_then_reconciles_in_its_own_transaction(
    monkeypatch, factory, db_session, make_user, make_settings, caplog
):
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    settings = make_settings()
    store = photo_service_store(settings)
    user = await make_user()
    orphan = await orphan_copy(db_session, user, store)
    monkeypatch.setattr(worker.asyncio, "sleep", sleep)
    monkeypatch.setattr(worker, "services", lambda: Shared(factory, settings))

    with caplog.at_level(logging.INFO, logger="tabsira.photos"):
        await worker.reconcile_photos_task.original_func()

    assert slept == [worker.RECONCILE_DELAY_SECONDS]
    assert await public_key_of(db_session, orphan) is None
    assert caplog.records[-1].getMessage() == (
        "public photo copies reconciled: 1 checked, 1 deleted, 0 failed"
    )


async def test_the_task_says_when_another_run_held_the_lock(
    monkeypatch, factory, make_settings, caplog
):
    async def skipped(db, store) -> ReconcileReport:
        return ReconcileReport(skipped=True)

    async def sleep(seconds: float) -> None:
        pass

    monkeypatch.setattr(worker.asyncio, "sleep", sleep)
    monkeypatch.setattr(worker, "services", lambda: Shared(factory, make_settings()))
    monkeypatch.setattr(photo_service, "reconcile_public_copies", skipped)

    with caplog.at_level(logging.INFO, logger="tabsira.photos"):
        await worker.reconcile_photos_task.original_func()

    assert caplog.records[-1].getMessage().endswith("(skipped: another run holds the lock)")


def photo_service_store(settings) -> PhotoStore:
    """The store the command builds from these settings: the test run's media directory."""
    from src.storage.photos import build_photo_store

    return build_photo_store(settings)


# ─── The hourly command ───


async def test_the_command_deletes_the_orphans_and_says_so(
    factory, db_session, make_user, make_settings, capsys
):
    settings = make_settings()
    store = photo_service_store(settings)
    orphan = await orphan_copy(db_session, await make_user(), store)

    assert await reconcile_photos.execute(settings, factory) == 0

    assert await public_key_of(db_session, orphan) is None
    assert capsys.readouterr().out == (
        "photos: 1 public copies checked, 1 deleted, 0 the store still refused\n"
    )


async def test_a_store_that_still_refuses_makes_the_command_exit_one(
    monkeypatch, factory, db_session, make_user, make_settings, capsys
):
    class Down(LocalStorage):
        async def delete(self, key: str) -> None:
            raise StorageUnavailableError("down")

    settings = make_settings()
    good = photo_service_store(settings)
    orphan = await orphan_copy(db_session, await make_user(), good)
    down = PhotoStore(
        Down(
            Path(settings.local_media_dir),
            base_url="https://api.tabsira.test",
            signing_key=b"k" * 32,
            default_ttl_seconds=300,
        ),
        settings,
    )
    monkeypatch.setattr(reconcile_photos, "build_photo_store", lambda _settings: down)

    assert await reconcile_photos.execute(settings, factory) == 1

    assert await public_key_of(db_session, orphan) is not None
    assert (
        "1 public copies checked, 0 deleted, 1 the store still refused" in capsys.readouterr().out
    )


async def test_the_command_steps_aside_when_another_run_holds_the_lock(
    monkeypatch, factory, make_settings, capsys
):
    async def skipped(db, store) -> ReconcileReport:
        return ReconcileReport(skipped=True)

    monkeypatch.setattr(reconcile_photos, "reconcile_public_copies", skipped)

    assert await reconcile_photos.execute(make_settings(), factory) == 0
    assert "another reconcile is running; nothing done" in capsys.readouterr().out


async def test_a_database_that_cannot_be_reached_exits_one_and_says_so(make_settings, capsys):
    def broken():
        raise OperationalError("select 1", {}, OSError("refused"))

    assert await reconcile_photos.execute(make_settings(), broken) == 1

    err = capsys.readouterr().err
    assert "Cannot reconcile the public photo copies (OperationalError)" in err


async def test_without_a_factory_the_application_engine_is_used_and_closed(
    monkeypatch, factory, make_settings
):
    closed = []

    async def dispose():
        closed.append(True)

    monkeypatch.setattr(reconcile_photos, "get_sessionmaker", lambda: factory)
    monkeypatch.setattr(reconcile_photos, "dispose_engine", dispose)

    assert await reconcile_photos.execute(make_settings()) == 0
    assert closed == [True]


def test_main_loads_the_settings_and_runs(monkeypatch, make_settings):
    seen = []

    async def fake(settings, session_factory=None):
        seen.append(settings)
        return 0

    monkeypatch.setattr(reconcile_photos, "execute", fake)
    monkeypatch.setattr(reconcile_photos, "load_settings", make_settings)

    assert reconcile_photos.main([]) == 0
    assert len(seen) == 1


def test_main_refuses_arguments_and_a_broken_configuration(monkeypatch, capsys):
    assert reconcile_photos.main(["--now"]) == 2
    assert "takes no arguments" in capsys.readouterr().err

    monkeypatch.setenv("ADMIN_AUDIT_RETENTION_DAYS", "7")

    assert reconcile_photos.main([]) == 1
    assert "ADMIN_AUDIT_RETENTION_DAYS" in capsys.readouterr().err
