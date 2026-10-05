"""
The community summary on the home page: aggregate counts of public things only.

The figures move slowly and the home page is the busiest page, so each worker keeps the answer
for ten minutes, one per set of switched-on features. Nothing personal is counted beyond what a
public page already shows: authors whose account is active and has a handle, entries shown on
the atlas, reactions whose counts are public (decision 61).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import ColumnElement, ScalarSelect, distinct, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock
from src.features import FeatureFlag
from src.models import MapEntry, MapEntryStatus
from src.models.social import Post, PostReaction, PostStatus, PostVisibility
from src.models.user import User
from src.schemas.community import CommunitySummary

CACHE_SECONDS = 600.0
# The whole count is bounded: a slow database must not hold the home page.
QUERY_TIMEOUT_SECONDS = 3.0

# The features that change what is counted; the others share one cached answer.
COUNTED = frozenset({FeatureFlag.SOCIAL, FeatureFlag.ATLAS, FeatureFlag.ATLAS_SPONSORSHIP})


@dataclass(frozen=True)
class _Held:
    expires_at: float
    summary: CommunitySummary


_cache: dict[frozenset[FeatureFlag], _Held] = {}


def forget() -> None:
    """Drop every cached answer (tests, and nothing else, need it)."""
    _cache.clear()


async def summary(db: AsyncSession, features: frozenset[FeatureFlag]) -> CommunitySummary:
    """Return the counts for these features, from the cache while it is fresh."""
    key = features & COUNTED
    now = clock.monotonic()
    held = _cache.get(key)
    if held is not None and held.expires_at > now:
        return held.summary
    async with asyncio.timeout(QUERY_TIMEOUT_SECONDS):
        counted = await _count(db, key)
    _cache[key] = _Held(now + CACHE_SECONDS, counted)
    return counted


def _visible_author() -> list[ColumnElement[bool]]:
    return [User.is_active.is_(True), User.deleted_at.is_(None), User.handle.isnot(None)]


def _public_post() -> list[ColumnElement[bool]]:
    return [Post.status == PostStatus.PUBLISHED, Post.visibility == PostVisibility.PUBLIC]


def _atlas_entries(column: ColumnElement[int], *where: ColumnElement[bool]) -> ScalarSelect[int]:
    # An orphaned entry is shown without its author (decision 60), so it needs no handle.
    shown = or_(
        (MapEntry.status == MapEntryStatus.PUBLISHED) & User.handle.isnot(None),
        MapEntry.status == MapEntryStatus.ORPHANED,
    )
    return (
        select(column)
        .select_from(MapEntry)
        .join(User, User.id == MapEntry.user_id)
        .where(User.is_active.is_(True), User.deleted_at.is_(None), shown, *where)
        .scalar_subquery()
    )


async def _count(db: AsyncSession, features: frozenset[FeatureFlag]) -> CommunitySummary:
    social = FeatureFlag.SOCIAL in features
    atlas = FeatureFlag.ATLAS in features
    sponsoring = FeatureFlag.ATLAS_SPONSORSHIP in features

    authored: list[ColumnElement[bool]] = []
    columns: dict[str, ScalarSelect[int]] = {}
    if social:
        authored.append(exists().where(Post.author_id == User.id, *_public_post()))
        columns["insights"] = (
            select(func.count())
            .select_from(Post)
            .join(User, User.id == Post.author_id)
            .where(*_public_post(), *_visible_author())
            .scalar_subquery()
        )
        columns["reactions"] = (
            select(func.count())
            .select_from(PostReaction)
            .join(Post, Post.id == PostReaction.post_id)
            .join(User, User.id == Post.author_id)
            .where(*_public_post(), *_visible_author())
            .scalar_subquery()
        )
    if atlas:
        authored.append(
            exists().where(MapEntry.user_id == User.id, MapEntry.status == MapEntryStatus.PUBLISHED)
        )
        columns["atlas_entries"] = _atlas_entries(func.count())
        columns["countries"] = _atlas_entries(
            func.count(distinct(MapEntry.country_iso2)), MapEntry.country_iso2.isnot(None)
        )
    if sponsoring:
        columns["sponsorships_open"] = _atlas_entries(
            func.count(), MapEntry.status == MapEntryStatus.ORPHANED
        )
    if not authored:
        # Neither the network nor the atlas is on: there is nothing public to count.
        return CommunitySummary(
            members=0,
            insights=None,
            reactions=None,
            atlas_entries=None,
            countries=None,
            sponsorships_open=None,
        )
    columns["members"] = (
        select(func.count())
        .select_from(User)
        .where(*_visible_author(), or_(*authored))
        .scalar_subquery()
    )
    row = (await db.execute(select(*(value.label(name) for name, value in columns.items())))).one()
    counts = row._asdict()
    return CommunitySummary(
        members=counts["members"],
        insights=counts.get("insights"),
        reactions=counts.get("reactions"),
        atlas_entries=counts.get("atlas_entries"),
        countries=counts.get("countries"),
        sponsorships_open=counts.get("sponsorships_open"),
    )
