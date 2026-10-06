"""Removing some mock insights whole, with what hangs on them, and never a real member's."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.cli.mock_drop import DependentRowsError, DropReport, drop_insights
from src.models import (
    Bookmark,
    Comment,
    CommentStatus,
    Insight,
    InsightPublication,
    MapEntry,
    Post,
    PostReaction,
    ReactionKind,
    Report,
    ReportReason,
    ReportTarget,
    Scan,
    User,
)
from src.models.atlas import MapEntrySponsorship
from src.models.timeseries import EvidenceExposure
from tests.test_import_mock import document, run, settings, world  # noqa: F401  (fixtures)

# Photo 12 holds insights i1 (post p1 with its reactions, bookmark and comments, an atlas entry)
# and i5 (post p2) of the test file.
PHOTO = 12


async def count(db: AsyncSession, model: Any, *conditions: Any) -> int:
    return int(await db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)


def of_photo(photo: int) -> Any:
    return Insight.photo_key.like(f"https://placepix.net/id/{photo}/%")


async def ids_of_photo(db: AsyncSession, photo: int) -> list[int]:
    return list((await db.scalars(select(Insight.id).where(of_photo(photo)))).all())


async def a_real_members_rows_on_the_photo(db: AsyncSession, make_user: Any) -> User:
    real = await make_user("real@example.com", verified=True)
    post = await db.scalar(select(Post).where(Post.reflection == "تأمل قصير"))
    assert post is not None
    db.add_all(
        [
            Comment(
                post_id=post.id, author_id=real.id, body="شكرا", status=CommentStatus.PUBLISHED
            ),
            PostReaction(post_id=post.id, user_id=real.id, kind=ReactionKind.JAZAK),
            Bookmark(post_id=post.id, user_id=real.id),
            Report(
                reporter_id=real.id,
                target_type=ReportTarget.POST,
                target_id=post.id,
                reason=ReportReason.OTHER,
            ),
        ]
    )
    await db.flush()
    return real


async def test_the_insights_go_with_their_scans_posts_entries_and_everything_on_them(
    db_session,
    settings,  # noqa: F811
    world,  # noqa: F811
):
    await run(db_session, settings, document())
    insights = await count(db_session, Insight)
    posts = await count(db_session, Post)
    scans = await count(db_session, Scan)
    entries = await count(db_session, MapEntry)
    ids = await ids_of_photo(db_session, PHOTO)
    assert len(ids) == 2

    report = await drop_insights(db_session, ids)

    assert (report.insights, report.posts, report.entries, report.dependents) == (2, 2, 1, {})
    assert await count(db_session, Insight) == insights - 2
    assert await count(db_session, Scan) == scans - 2
    assert await count(db_session, Post) == posts - 2
    assert await count(db_session, MapEntry) == entries - 1
    for model in (Comment, PostReaction, Bookmark):
        assert await count(db_session, model) == 0
    left = select(Insight.id)
    assert (
        await count(db_session, InsightPublication, ~InsightPublication.insight_id.in_(left)) == 0
    )
    assert await count(db_session, EvidenceExposure, ~EvidenceExposure.insight_id.in_(left)) == 0
    # Safe to run again: nothing left to find.
    assert await drop_insights(db_session, ids) == DropReport()


async def test_no_ids_or_ids_of_nothing_change_nothing(
    db_session,
    settings,  # noqa: F811
    world,  # noqa: F811
):
    await run(db_session, settings, document())
    before = await count(db_session, Insight)

    assert await drop_insights(db_session, []) == DropReport()
    assert await drop_insights(db_session, [10**12]) == DropReport()
    assert await count(db_session, Insight) == before


async def test_a_real_members_insight_is_never_removed(
    db_session,
    settings,  # noqa: F811
    world,  # noqa: F811
    make_user,
):
    await run(db_session, settings, document())
    real = await make_user("owner@example.com", verified=True)
    ids = await ids_of_photo(db_session, 16)
    kept = await db_session.get(Insight, ids[0])
    assert kept is not None
    # Not a state the app makes (a real photo key is never a placepix address): the scope holds anyway.
    kept.user_id = real.id
    await db_session.flush()

    report = await drop_insights(db_session, ids)

    assert report.insights == len(ids) - 1
    assert await db_session.get(Insight, kept.id) is not None


async def test_a_real_members_rows_refuse_the_drop_until_the_flag_allows_it(
    db_session,
    settings,  # noqa: F811
    world,  # noqa: F811
    make_user,
):
    await run(db_session, settings, document())
    real = await a_real_members_rows_on_the_photo(db_session, make_user)
    ids = await ids_of_photo(db_session, PHOTO)

    with pytest.raises(DependentRowsError, match="--also-dependent-rows") as refused:
        await drop_insights(db_session, ids)
    for kind in ("comments or replies 1", "reactions 1", "bookmarks 1", "reports 1"):
        assert kind in str(refused.value)
    assert await count(db_session, Insight, of_photo(PHOTO)) == 2

    report = await drop_insights(db_session, ids, also_dependent_rows=True)

    assert report.dependents == {
        "comments or replies": 1,
        "reactions": 1,
        "bookmarks": 1,
        "reports": 1,
    }
    assert await count(db_session, Report) == 0
    assert await db_session.get(User, real.id) is not None


async def test_a_real_sponsor_of_an_entry_is_counted(
    db_session,
    settings,  # noqa: F811
    world,  # noqa: F811
    make_user,
):
    await run(db_session, settings, document())
    real = await make_user("sponsor@example.com", verified=True)
    entry = await db_session.scalar(
        select(MapEntry).join(Insight, Insight.id == MapEntry.insight_id).where(of_photo(PHOTO))
    )
    assert entry is not None
    db_session.add(MapEntrySponsorship(entry_id=entry.id, user_id=real.id))
    await db_session.flush()

    with pytest.raises(DependentRowsError, match="sponsorships 1"):
        await drop_insights(db_session, await ids_of_photo(db_session, PHOTO))
