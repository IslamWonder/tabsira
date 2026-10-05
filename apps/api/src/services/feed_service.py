"""
What a reader may see in a list of posts, and the pages of each list.

`readable_posts` is the one place that decides which published posts a viewer may be shown, so
the feeds, a profile and the bookmarks cannot come to disagree: only published posts, of
accounts that are active and have a public identity, in the audience the viewer belongs to, and
none of anyone the viewer has blocked or who has blocked the viewer. Every list pages by a
keyset cursor on `(published_at, id)`, so a post published or withdrawn between two pages
neither repeats nor skips an item. Nothing here invents a post: a list with nothing in it is
empty and says why.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import Select, select, tuple_, union
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock
from src.models.profile import Profile
from src.models.social import (
    Bookmark,
    Comment,
    Follow,
    InsightPublication,
    Post,
    PostLike,
    PostStatus,
    PostVisibility,
)
from src.models.user import User
from src.schemas.social import WhyOut
from src.services import cursor as cursors
from src.services import public_identity, ranking
from src.services.block_service import blocked_with
from src.services.post_service import PostRow

# How many of the newest readable posts the «لك» feed ranks. A bound, so the work of a page
# does not grow with the network.
CANDIDATES = 200


@dataclass
class Page:
    """A page of posts, the cursor of the next one, and why a first page has nothing."""

    rows: list[PostRow]
    next_cursor: str | None
    why: dict[int, WhyOut] = field(default_factory=dict)


def readable_posts(
    viewer: User | None, *, public_only: bool = False
) -> Select[Post, InsightPublication, User]:
    """Select the published posts `viewer` (None for a guest) may be shown, unordered."""
    statement = (
        select(Post, InsightPublication, User)
        .join(InsightPublication, InsightPublication.id == Post.publication_id)
        .join(User, User.id == Post.author_id)
        .where(
            Post.status == PostStatus.PUBLISHED,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
            User.handle.is_not(None),
        )
    )
    if viewer is None or public_only:
        statement = statement.where(Post.visibility == PostVisibility.PUBLIC)
    else:
        followed = select(Follow.followee_id).where(Follow.follower_id == viewer.id)
        statement = statement.where(
            (Post.visibility == PostVisibility.PUBLIC)
            | (Post.author_id == viewer.id)
            | Post.author_id.in_(followed)
        )
    if viewer is not None:
        statement = statement.where(Post.author_id.not_in(blocked_with(viewer.id)))
    return statement


async def _newest_first(
    db: AsyncSession,
    statement: Select[Post, InsightPublication, User],
    cursor: cursors.Cursor | None,
    limit: int,
) -> Page:
    """Page a list of posts newest first by `(published_at, id)`."""
    ordered = statement.order_by(Post.published_at.desc(), Post.id.desc()).limit(limit + 1)
    if cursor is not None:
        ordered = ordered.where(tuple_(Post.published_at, Post.id) < tuple_(cursor.at, cursor.id))
    found = (await db.execute(ordered)).all()
    rows = [PostRow(post, publication, author) for post, publication, author in found[:limit]]
    next_cursor = None
    if len(found) > limit:
        last = rows[-1].post
        next_cursor = cursors.encode(cursors.Cursor(at=_published_at(last), id=last.id))
    return Page(rows, next_cursor)


async def follows_anyone(db: AsyncSession, viewer: User) -> bool:
    return (
        await db.scalar(select(Follow.follower_id).where(Follow.follower_id == viewer.id).limit(1))
    ) is not None


async def following(
    db: AsyncSession, viewer: User, cursor: cursors.Cursor | None, limit: int
) -> Page:
    """Page «أتابع»: the posts of the accounts the viewer follows, newest first."""
    followed = select(Follow.followee_id).where(Follow.follower_id == viewer.id)
    return await _newest_first(
        db, readable_posts(viewer).where(Post.author_id.in_(followed)), cursor, limit
    )


async def latest(
    db: AsyncSession, viewer: User | None, cursor: cursors.Cursor | None, limit: int
) -> Page:
    """Every public post, newest first."""
    return await _newest_first(db, readable_posts(viewer, public_only=True), cursor, limit)


async def by_member(
    db: AsyncSession, member: User, viewer: User | None, cursor: cursors.Cursor | None, limit: int
) -> Page:
    """List a member's published posts that `viewer` may read, newest first."""
    return await _newest_first(
        db, readable_posts(viewer).where(Post.author_id == member.id), cursor, limit
    )


async def bookmarked(
    db: AsyncSession, viewer: User, cursor: cursors.Cursor | None, limit: int
) -> Page:
    """List the posts the viewer saved and may still read, the latest save first."""
    statement = (
        readable_posts(viewer)
        .add_columns(Bookmark.created_at)
        .join(Bookmark, (Bookmark.post_id == Post.id) & (Bookmark.user_id == viewer.id))
        .order_by(Bookmark.created_at.desc(), Post.id.desc())
        .limit(limit + 1)
    )
    if cursor is not None:
        statement = statement.where(
            tuple_(Bookmark.created_at, Post.id) < tuple_(cursor.at, cursor.id)
        )
    found = (await db.execute(statement)).all()
    page = found[:limit]
    rows = [PostRow(post, publication, author) for post, publication, author, _ in page]
    next_cursor = None
    if len(found) > limit:
        *_, saved_at = page[-1]
        next_cursor = cursors.encode(cursors.Cursor(at=saved_at, id=page[-1][0].id))
    return Page(rows, next_cursor)


# ─── «لك» ──────────────────────────────────────────────────────────────────────


async def seen_post_ids(db: AsyncSession, viewer: User, post_ids: list[int]) -> set[int]:
    """
    Return which of these posts the viewer has already met.

    Met means the viewer's own doing: they liked it, saved it or commented on it. Opening a post
    is not recorded anywhere, so it is not counted. When the learner's insight exposures
    (decision 13) exist, this is where they are added: a post about an insight the learner has
    already been shown is met too.
    """
    met = union(
        select(PostLike.post_id).where(
            PostLike.user_id == viewer.id, PostLike.post_id.in_(post_ids)
        ),
        select(Bookmark.post_id).where(
            Bookmark.user_id == viewer.id, Bookmark.post_id.in_(post_ids)
        ),
        select(Comment.post_id).where(
            Comment.author_id == viewer.id, Comment.post_id.in_(post_ids)
        ),
    )
    return set(await db.scalars(met))


async def personalised(db: AsyncSession, viewer: User | None) -> bool:
    """Whether the viewer's own signals may shape their feed: signed in, and not switched off."""
    if viewer is None:
        return False
    switch = await db.scalar(
        select(Profile.personalization_enabled).where(Profile.user_id == viewer.id)
    )
    return switch is not False


async def for_you(
    db: AsyncSession, viewer: User | None, cursor: cursors.Cursor | None, limit: int
) -> Page:
    """
    «لك»: the newest readable posts, ranked and explained.

    The list is ranked as of one moment, pinned in the cursor, so scrolling continues the list
    that was computed and a post published meanwhile waits for the next refresh. Freshness,
    follows, variety and what the viewer has met are the only inputs (see `ranking`).
    """
    as_of = cursor.as_of if cursor is not None and cursor.as_of is not None else clock.utcnow()
    statement = readable_posts(viewer).where(Post.published_at <= as_of)
    if viewer is not None:
        statement = statement.where(Post.author_id != viewer.id)
    found = (
        await db.execute(
            statement.order_by(Post.published_at.desc(), Post.id.desc()).limit(CANDIDATES)
        )
    ).all()
    rows = {row.post.id: row for row in (PostRow(*found_row) for found_row in found)}
    switched_on = await personalised(db, viewer)
    followed: set[uuid.UUID] = set()
    seen: set[int] = set()
    if viewer is not None and switched_on:
        followed = set(
            await db.scalars(select(Follow.followee_id).where(Follow.follower_id == viewer.id))
        )
        seen = await seen_post_ids(db, viewer, list(rows))
    candidates = [
        ranking.Candidate(
            post_id=row.post.id,
            author_id=row.post.author_id,
            author_name=public_identity.shown_name(row.author) or row.author.handle or "",
            published_at=_published_at(row.post),
            concepts=tuple(row.publication.concepts) if row.publication else (),
        )
        for row in rows.values()
    ]
    ranked = ranking.rank(
        candidates, now=as_of, followed=followed, seen=seen, personalise=switched_on
    )
    rest = ranking.after(ranked, cursor.score if cursor else None, cursor.id if cursor else None)
    shown = rest[:limit]
    next_cursor = None
    if len(rest) > limit:
        last = shown[-1]
        next_cursor = cursors.encode(
            cursors.Cursor(
                at=last.candidate.published_at,
                id=last.candidate.post_id,
                as_of=as_of,
                score=last.score,
            )
        )
    return Page(
        [rows[item.candidate.post_id] for item in shown],
        next_cursor,
        {item.candidate.post_id: item.why for item in shown},
    )


def _published_at(post: Post) -> datetime:
    """Return when a published post went out; the constraint `published_has_time` guarantees it."""
    return post.published_at or post.created_at
