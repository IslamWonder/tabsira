"""
Reactions and bookmarks: one of each per account and post, safe to repeat.

A reaction («انتفعتُ بها» or «جزاك الله خيرًا», decision 61) is counted from its rows and shown
as a number; who reacted is never listed. A bookmark is private: nobody sees whose it is, and
nobody counts it. Neither is a counter on the post, so neither can drift.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.social import Bookmark, PostReaction, ReactionKind
from src.models.user import User
from src.schemas.social import ReactionCountsOut, ReactionOut


def counts_of(by_kind: dict[ReactionKind, int]) -> ReactionCountsOut:
    return ReactionCountsOut(
        benefited=by_kind.get(ReactionKind.BENEFITED, 0), jazak=by_kind.get(ReactionKind.JAZAK, 0)
    )


async def counts(db: AsyncSession, post_ids: list[int]) -> dict[int, ReactionCountsOut]:
    """Count each kind of reaction for these posts, in one query; a post with none is absent."""
    rows = await db.execute(
        select(PostReaction.post_id, PostReaction.kind, func.count())
        .where(PostReaction.post_id.in_(post_ids))
        .group_by(PostReaction.post_id, PostReaction.kind)
    )
    found: dict[int, dict[ReactionKind, int]] = {}
    for post_id, kind, number in rows.all():
        found.setdefault(post_id, {})[kind] = number
    return {post_id: counts_of(by_kind) for post_id, by_kind in found.items()}


async def mine(db: AsyncSession, post_ids: list[int], user: User) -> dict[int, list[ReactionKind]]:
    """Return the kinds the user gave to each of these posts, in the order of the enum."""
    rows = await db.execute(
        select(PostReaction.post_id, PostReaction.kind).where(
            PostReaction.user_id == user.id, PostReaction.post_id.in_(post_ids)
        )
    )
    given: dict[int, set[ReactionKind]] = {}
    for post_id, kind in rows.all():
        given.setdefault(post_id, set()).add(kind)
    return {
        post_id: [kind for kind in ReactionKind if kind in kinds]
        for post_id, kinds in given.items()
    }


async def state(db: AsyncSession, post_id: int, user: User) -> ReactionOut:
    """Return the post's counts and the kinds the caller gave: the answer of both routes."""
    return ReactionOut(
        reactions=(await counts(db, [post_id])).get(post_id, counts_of({})),
        mine=(await mine(db, [post_id], user)).get(post_id, []),
    )


async def react(db: AsyncSession, post_id: int, user: User, kind: ReactionKind) -> None:
    """Add the caller's reaction; reacting again with the same kind changes nothing."""
    await db.execute(
        insert(PostReaction)
        .values(post_id=post_id, user_id=user.id, kind=kind)
        .on_conflict_do_nothing(
            index_elements=[PostReaction.post_id, PostReaction.user_id, PostReaction.kind]
        )
    )


async def unreact(db: AsyncSession, post_id: int, user: User, kind: ReactionKind) -> None:
    await db.execute(
        delete(PostReaction).where(
            PostReaction.post_id == post_id,
            PostReaction.user_id == user.id,
            PostReaction.kind == kind,
        )
    )


async def bookmark(db: AsyncSession, post_id: int, user: User) -> None:
    """Save the post for the caller; saving again changes nothing."""
    await db.execute(
        insert(Bookmark)
        .values(post_id=post_id, user_id=user.id)
        .on_conflict_do_nothing(index_elements=[Bookmark.user_id, Bookmark.post_id])
    )


async def unbookmark(db: AsyncSession, post_id: int, user: User) -> None:
    await db.execute(
        delete(Bookmark).where(Bookmark.post_id == post_id, Bookmark.user_id == user.id)
    )
