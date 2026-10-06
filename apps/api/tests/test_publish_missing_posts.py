# ruff: noqa: F811
"""The command that gives every basira published before decision 68 its post."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker

from src import clock
from src.cli import publish_missing_posts as command
from src.config import Environment, Settings
from src.models import (
    AgeRange,
    Insight,
    MapEntryStatus,
    Post,
    PostStatus,
    RemovalSource,
)
from src.models.profile import Profile
from src.services import insight_post_service
from src.storage.photos import build_photo_store
from tests.support_orphans import entry_row
from tests.support_social import make_member, new_post, scripture  # noqa: F401  (fixtures)
from tests.test_atlas import EVIDENCE, _insight
from tests.test_import_mock import settings  # noqa: F401  (fixture)

URL = "postgresql+asyncpg://u:p@127.0.0.1:5432/"


async def public_insight(db, member, **values: Any) -> Insight:
    found = await db.get(Insight, await _insight(db, member, **EVIDENCE | values))
    found.published_at = clock.utcnow()
    await db.flush()
    return found


async def run(db, settings, **options: Any) -> command.Report:
    return await command.publish_missing(db, settings, build_photo_store(settings), **options)


async def all_posts(db) -> list[Post]:
    found = await db.scalars(select(Post).execution_options(populate_existing=True))
    return list(found.all())


async def test_a_public_insight_gets_a_public_post_once(
    db_session, settings, make_member, scripture
):
    member = await make_member("amal")
    await public_insight(db_session, member)

    first = await run(db_session, settings)
    second = await run(db_session, settings)

    (post,) = await all_posts(db_session)
    assert (post.status, post.reflection, post.author_id) == (
        PostStatus.PUBLISHED,
        None,
        member.user.id,
    )
    assert first.published == 1
    assert second.published == 0
    assert second.skipped == {"already posted": 1}


async def test_a_published_atlas_entry_is_a_candidate_and_an_orphaned_one_is_not(
    db_session, settings, make_member, scripture
):
    member = await make_member("amal")
    shown = await entry_row(db_session, member)
    await entry_row(db_session, member, status=MapEntryStatus.ORPHANED)

    report = await run(db_session, settings)

    (post,) = await all_posts(db_session)
    assert report.published == 1
    assert report.skipped == {}
    assert post.publication_id is not None
    assert shown.insight_id is not None


async def test_the_photo_is_asked_for_when_the_owner_already_chose_it(
    db_session, settings, make_member, scripture, monkeypatch
):
    member = await make_member("amal")
    with_photo = await entry_row(db_session, member, with_photo=True)
    without = await entry_row(db_session, member, with_photo=False)
    copy = await public_insight(db_session, member, photo_public_key="public/x.jpg")
    asked: dict[int, bool] = {}
    real = insight_post_service.ensure_post

    async def spy(db, source, author, insight_id, *rest: Any, publish_photo: bool = False):
        asked[insight_id] = publish_photo
        return await real(db, source, author, insight_id, *rest, publish_photo=publish_photo)

    monkeypatch.setattr(insight_post_service, "ensure_post", spy)

    report = await run(db_session, settings)

    assert report.published == 3
    assert asked == {with_photo.insight_id: True, without.insight_id: False, copy.id: False}


async def test_every_skip_is_counted_by_its_reason(db_session, settings, make_member, scripture):
    closed = await make_member("closed")
    gone = await make_member("gone")
    closed.user.is_active = False
    gone.user.deleted_at = clock.utcnow()
    unverified = await make_member("unverified", verified=False)
    nameless = await make_member("nameless", identity=False)
    posted = await make_member("posted")
    withdrew = await make_member("withdrew")
    for member in (closed, gone, unverified, nameless, withdrew):
        await public_insight(db_session, member)
    held = await public_insight(db_session, posted)
    await insight_post_service.ensure_post(
        db_session,
        command.InsightTableSource(),
        posted.user,
        held.id,
        settings,
        command.NoTextGuard(),
        build_photo_store(settings),
    )
    await new_post(
        db_session,
        withdrew.user,
        status=PostStatus.REMOVED,
        removal_source=RemovalSource.OWNER,
        removed_at=clock.utcnow(),
    )

    report = await run(db_session, settings)

    assert report.skipped == {
        "account closed": 2,
        "address not verified": 1,
        "no public handle": 1,
        "already posted": 1,
        "owner withdrew a post since": 1,
    }
    assert report.published == 0
    assert report.lines()[0] == "posts published: 0"
    assert "skipped, already posted: 1" in report.lines()


async def test_a_refused_insight_is_counted_with_its_code_and_rolled_back(
    db_session, settings, make_member, scripture
):
    young = await make_member("young")
    fine = await make_member("fine")
    await public_insight(db_session, young)
    await public_insight(db_session, fine)
    profile = await db_session.get(Profile, young.user.id)
    profile.age_range = AgeRange.UNDER_13
    # Committed as in production, so the refusal's rollback undoes only the refused insight.
    await db_session.commit()

    report = await run(db_session, settings)

    assert report.skipped == {"refused (UNDER_13_CANNOT_PUBLISH)": 1}
    assert report.published == 1
    assert [post.author_id for post in await all_posts(db_session)] == [fine.user.id]


async def test_a_dry_run_counts_and_writes_nothing(db_session, settings, make_member, scripture):
    member = await make_member("amal")
    await public_insight(db_session, member)

    report = await run(db_session, settings, dry_run=True)

    assert report.published == 1
    assert await all_posts(db_session) == []


async def test_only_mock_accounts_are_taken_when_asked(
    db_session, settings, make_member, scripture
):
    mock = await make_member("mocked")
    real = await make_member("real")
    mock.user.email = "mocked@mock.tabsira.me"
    await public_insight(db_session, mock)
    await public_insight(db_session, real)
    await db_session.flush()

    report = await run(db_session, settings, only_mock=True)

    assert report.published == 1
    assert [post.author_id for post in await all_posts(db_session)] == [mock.user.id]


async def test_the_guard_of_this_command_is_never_asked():
    with pytest.raises(AssertionError):
        await command.NoTextGuard().check("text")


def test_what_may_run_and_where(make_settings):
    development = make_settings(database_url=URL + "tabsira")
    test = make_settings(database_url=URL + "tabsira_test")
    template = make_settings(database_url=URL + "tabsira_template")
    production = development.model_copy(update={"environment": Environment.PRODUCTION})

    def check(given: Settings, **flags: bool) -> str | None:
        options = {"i_understand": True, "allow_production": False, "allow_test_database": False}
        return command.check_allowed(given, **options | flags)

    assert "--i-understand" in str(check(development, i_understand=False))
    assert "test database" in str(check(test))
    assert "test database" in str(check(template))
    assert "--allow-production" in str(check(production))
    assert check(development) is None
    assert check(test, allow_test_database=True) is None
    assert check(production, allow_production=True) is None


def args(*argv: str) -> Any:
    return command._arguments(list(argv))


async def test_execute_refuses_then_reports_a_dry_run(
    db_session, settings, make_member, scripture, capsys
):
    member = await make_member("amal")
    await public_insight(db_session, member)
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)

    refused = await command.execute(args(), settings, factory, allow_test_database=True)
    done = await command.execute(
        args("--i-understand", "--dry-run"), settings, factory, allow_test_database=True
    )

    assert (refused, done) == (1, 0)
    captured = capsys.readouterr()
    assert "--i-understand" in captured.err
    assert "posts published: 1" in captured.out


async def test_execute_reports_an_unreachable_database(settings, capsys):
    def down() -> Any:
        raise OperationalError("select 1", {}, OSError("down"))

    code = await command.execute(
        args("--i-understand"),
        settings,
        down,
        allow_test_database=True,  # type: ignore[arg-type]
    )

    assert code == 1
    assert "Cannot reach the database" in capsys.readouterr().err


async def test_without_a_session_factory_the_engine_is_used_and_closed(
    db_session, settings, monkeypatch
):
    closed: list[bool] = []

    async def dispose() -> None:
        closed.append(True)

    monkeypatch.setattr(
        command,
        "get_sessionmaker",
        lambda: async_sessionmaker(bind=db_session.bind, expire_on_commit=False),
    )
    monkeypatch.setattr(command, "dispose_engine", dispose)

    code = await command.execute(args("--i-understand"), settings, allow_test_database=True)

    assert code == 0
    assert closed == [True]


def test_main_builds_the_settings_and_runs(monkeypatch, settings):
    async def execute(parsed: Any, given: Settings) -> int:
        assert given is settings
        return 7

    monkeypatch.setattr(command, "load_settings", lambda: settings)
    monkeypatch.setattr(command, "execute", execute)

    assert command.main(["--i-understand"]) == 7


def test_main_reports_a_broken_configuration(monkeypatch, capsys):
    def broken() -> Settings:
        raise command.ConfigError("no database")

    monkeypatch.setattr(command, "load_settings", broken)

    assert command.main(["--i-understand"]) == 1
    assert "no database" in capsys.readouterr().err
