"""
`GET /community/summary`: aggregate counts of public things only, cached, and a 503 that never
holds the home page when the database is down.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock
from src.features import FeatureFlag
from src.models import MapEntryStatus
from src.models.social import PostReaction, PostStatus, PostVisibility, ReactionKind
from src.models.user import User
from src.services import community_service
from tests import geo_dataset as world_data
from tests.helpers import client_for
from tests.support_orphans import entry_row
from tests.support_social import Member, new_post

ALL = frozenset(FeatureFlag)
FIELDS = {"members", "insights", "reactions", "atlas_entries", "countries", "sponsorships_open"}


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    community_service.forget()


def _member(user: User) -> Member:
    return Member(user, None, user.handle)  # type: ignore[arg-type]


async def _community(db: AsyncSession, make_user: Callable[..., Any]) -> None:
    """
    Two visible members, one account without a handle, one deleted account, one inactive.

    Counted: a's public post and its one reaction from b, a's entry in Mecca, b's in Tunis, and
    the orphaned entry of the handle-less account (shown without its author, decision 60).
    """
    a = await make_user("a@example.com", handle="alpha")
    b = await make_user("b@example.com", handle="beta")
    nameless = await make_user("c@example.com")
    gone = await make_user("d@example.com", handle="gone", deleted_at=clock.utcnow())
    idle = await make_user("e@example.com", handle="idle", is_active=False)

    public = await new_post(db, a, status=PostStatus.PUBLISHED)
    followers = await new_post(
        db, a, status=PostStatus.PUBLISHED, visibility=PostVisibility.FOLLOWERS
    )
    await new_post(db, b)  # a draft
    await new_post(db, b, status=PostStatus.PENDING_REVIEW)
    await new_post(db, nameless, status=PostStatus.PUBLISHED)
    await new_post(db, gone, status=PostStatus.PUBLISHED)
    db.add_all(
        [
            PostReaction(post_id=public.id, user_id=b.id, kind=ReactionKind.BENEFITED),
            PostReaction(post_id=public.id, user_id=b.id, kind=ReactionKind.JAZAK),
            PostReaction(post_id=followers.id, user_id=b.id, kind=ReactionKind.BENEFITED),
        ]
    )
    await entry_row(db, _member(a), place=world_data.MECCA_CITY)
    await entry_row(db, _member(b))
    await entry_row(db, _member(b), status=MapEntryStatus.DRAFT)
    await entry_row(db, _member(nameless), status=MapEntryStatus.ORPHANED)
    await entry_row(db, _member(nameless))  # published, but its author has no handle
    await entry_row(db, _member(idle), place=None)
    await db.flush()


async def test_counts_public_things_only(
    account_app: FastAPI,
    db_session: AsyncSession,
    make_user: Callable[..., Any],
    scripture: None,
) -> None:
    await world_data.load_world(db_session)
    await _community(db_session, make_user)

    async with client_for(account_app) as http:
        response = await http.get("/community/summary")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == FIELDS
    assert body == {
        "members": 2,
        "insights": 1,
        "reactions": 2,
        "atlas_entries": 3,
        "countries": 2,
        "sponsorships_open": 1,
    }


async def test_a_feature_switched_off_is_not_counted(db_session: AsyncSession) -> None:
    no_social = await community_service.summary(db_session, ALL - {FeatureFlag.SOCIAL})
    assert no_social.insights is None
    assert no_social.reactions is None
    assert no_social.atlas_entries == 0

    no_sponsoring = await community_service.summary(
        db_session, ALL - {FeatureFlag.ATLAS_SPONSORSHIP}
    )
    assert no_sponsoring.sponsorships_open is None
    assert no_sponsoring.countries == 0

    only_social = await community_service.summary(db_session, frozenset({FeatureFlag.SOCIAL}))
    assert only_social.atlas_entries is None
    assert only_social.countries is None
    assert only_social.insights == 0


async def test_nothing_public_is_on_reads_nothing() -> None:
    class NoDatabase:
        async def execute(self, *_args: Any) -> None:
            raise AssertionError("no query while nothing public is switched on")

    summary = await community_service.summary(
        NoDatabase(),  # type: ignore[arg-type]
        frozenset({FeatureFlag.CHAT}),
    )
    assert summary.model_dump() == dict.fromkeys(FIELDS) | {"members": 0}


async def test_the_answer_is_kept_ten_minutes(
    db_session: AsyncSession, make_user: Callable[..., Any], moving_clock: Any
) -> None:
    first = await community_service.summary(db_session, ALL)
    author = await make_user("a@example.com", handle="alpha")
    await new_post(db_session, author, status=PostStatus.PUBLISHED)

    # Features that do not change what is counted share the cached answer.
    assert await community_service.summary(db_session, ALL - {FeatureFlag.CHAT}) == first
    moving_clock.advance(seconds=community_service.CACHE_SECONDS - 1)
    assert (await community_service.summary(db_session, ALL)).insights == 0

    moving_clock.advance(seconds=2)
    later = await community_service.summary(db_session, ALL)
    assert later.insights == 1
    assert later.members == 1


async def test_a_slow_database_is_cut_short(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def hangs(*_args: Any) -> None:
        await asyncio.sleep(1)

    monkeypatch.setattr(community_service, "QUERY_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(community_service, "_count", hangs)
    with pytest.raises(TimeoutError):
        await community_service.summary(db_session, ALL)


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("SELECT", {}, ConnectionRefusedError()),
        ConnectionRefusedError(),
        TimeoutError(),
    ],
)
async def test_a_database_that_is_down_answers_503(
    account_app: FastAPI, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    async def fails(*_args: Any) -> None:
        raise error

    monkeypatch.setattr(community_service, "summary", fails)
    async with client_for(account_app) as http:
        response = await http.get("/community/summary")

    assert response.status_code == 503
    assert response.json()["error"] == "SERVICE_UNAVAILABLE"
