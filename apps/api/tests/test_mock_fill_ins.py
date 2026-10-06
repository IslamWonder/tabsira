"""Fill-ins: a feature added after the mock import, written onto the mock rows that are there."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.cli import import_mock, mock_fill_ins
from src.models import Post, PostStatus, PostVisibility, User
from tests.support_social import new_post
from tests.test_import_mock import document, run, settings, world  # noqa: F401  (fixtures)


async def views_by_post(db) -> dict[int, tuple[int, PostVisibility]]:
    rows = await db.execute(
        select(Post.id, Post.views_count, Post.visibility).execution_options(populate_existing=True)
    )
    return {post_id: (views, visibility) for post_id, views, visibility in rows}


async def imported_without_views(db, settings) -> None:  # noqa: F811
    await run(db, settings, document())
    # As a file written before task 16.3 leaves them.
    await db.execute(update(Post).values(views_count=0))


async def test_views_fill_every_mock_post_plausibly_and_a_second_run_changes_nothing(
    db_session,
    settings,  # noqa: F811
    world,  # noqa: F811
):
    await imported_without_views(db_session, settings)
    posts = (await db_session.scalars(select(Post))).all()
    assert posts

    changed = await mock_fill_ins.fill_views(db_session)

    filled = await views_by_post(db_session)
    assert changed == len(posts)
    assert all(views > 0 for views, _ in filled.values())
    by_author = await db_session.scalar(
        select(Post).join(User, User.id == Post.author_id).where(User.handle == "amal_tn")
    )
    # amal's first post: two members reacted, saved or commented, so at least two views.
    assert by_author is not None
    assert filled[by_author.id][0] >= 2
    assert await mock_fill_ins.fill_views(db_session) == 0
    assert await views_by_post(db_session) == filled


async def test_views_never_lower_a_count_and_never_touch_a_real_members_post(
    db_session,
    settings,  # noqa: F811
    world,  # noqa: F811
    make_user,
):
    await imported_without_views(db_session, settings)
    real = await make_user("real@example.com", verified=True)
    theirs = await new_post(db_session, real, status=PostStatus.PUBLISHED)
    busy = (await db_session.scalars(select(Post).where(Post.id != theirs.id))).first()
    assert busy is not None
    await db_session.execute(update(Post).where(Post.id == busy.id).values(views_count=10**6))

    await mock_fill_ins.fill_views(db_session)

    after = await views_by_post(db_session)
    assert after[theirs.id][0] == 0
    assert after[busy.id][0] == 10**6


def test_plausible_views_are_stable_and_a_followers_only_post_reaches_fewer():
    first = mock_fill_ins.plausible_views(7, 3, public=True)
    assert first == mock_fill_ins.plausible_views(7, 3, public=True)
    assert first >= 3
    assert mock_fill_ins.plausible_views(7, 3, public=False) < first
    assert mock_fill_ins.plausible_views(7, 50, public=False) >= 50


def args(*argv: str) -> Any:
    return import_mock._arguments(list(argv))


def test_fill_in_is_given_alone_and_by_a_known_name():
    assert args("--fill-in", "views", "--i-understand").fill_ins == ["views"]
    for bad in (
        ["--fill-in", "nothing", "--i-understand"],
        ["--fill-in", "views", "--clean"],
        ["f.json", "--fill-in", "views"],
    ):
        with pytest.raises(SystemExit):
            args(*bad)


async def test_execute_fills_in_once_per_name_and_says_how_many(
    db_session,
    settings,  # noqa: F811
    world,  # noqa: F811
    capsys,
):
    await imported_without_views(db_session, settings)
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)

    refused = await import_mock.execute(
        args("--fill-in", "views"), settings, factory, allow_test_database=True
    )
    done = await import_mock.execute(
        args("--fill-in", "views", "--fill-in", "views", "--i-understand"),
        settings,
        factory,
        allow_test_database=True,
    )

    assert (refused, done) == (1, 0)
    out = capsys.readouterr().out
    assert out.count("views:") == 1
    assert "mock rows filled in" in out
