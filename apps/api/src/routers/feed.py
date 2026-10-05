"""
The feeds: «أتابع», «لك» and the latest, and a member's own posts.

All of them page by a cursor, show only what the viewer may read, and say so when there is
nothing to show: an empty feed is empty, and no post is ever invented to fill it. «لك» explains
each item with a short reason («لماذا أرى هذا؟»).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from src.deps import CurrentUser, DbDep, OptionalUser, PhotoStoreDep, require_social
from src.models.user import User
from src.schemas.social import FeedPage
from src.services import cursor as cursors
from src.services import feed_service, member_service, post_view
from src.services.feed_service import Page
from src.storage.photos import PhotoStore

router = APIRouter(tags=["feed"], dependencies=[Depends(require_social)])

type EmptyReason = Literal["follows_nobody", "no_posts"]

PAGE_DEFAULT = 20
PAGE_MAX = 50
Limit = Query(PAGE_DEFAULT, ge=1, le=PAGE_MAX, description="Posts in the page")


async def _page(
    db: DbDep,
    page: Page,
    viewer: User | None,
    cursor: str | None,
    photos: PhotoStore,
    empty_reason: EmptyReason = "no_posts",
) -> FeedPage:
    items = await post_view.build_posts(db, page.rows, viewer, photos=photos, why=page.why or None)
    reason = empty_reason if cursor is None and not items else None
    return FeedPage(items=items, next_cursor=page.next_cursor, empty_reason=reason)


@router.get("/feed/following", summary="«أتابع»: the posts of the members the caller follows")
async def feed_following(
    user: CurrentUser,
    db: DbDep,
    photos: PhotoStoreDep,
    cursor: str | None = None,
    limit: int = Limit,
) -> FeedPage:
    """
    Return the posts of the members the caller follows, newest first.

    Followers-only posts of those members are included. `empty_reason` is `follows_nobody` when
    the caller follows no one and `no_posts` when those they follow have published nothing.
    """
    page = await feed_service.following(db, user, cursors.decode(cursor), limit)
    reason: EmptyReason = "no_posts"
    if not page.rows and cursor is None and not await feed_service.follows_anyone(db, user):
        reason = "follows_nobody"
    return await _page(db, page, user, cursor, photos, reason)


@router.get("/feed/for-you", summary="«لك»: a ranked feed with the reason for each post")
async def feed_for_you(
    viewer: OptionalUser,
    db: DbDep,
    photos: PhotoStoreDep,
    cursor: str | None = None,
    limit: int = Limit,
) -> FeedPage:
    """
    Return the newest readable posts, ranked, each with `why` («لماذا أرى هذا؟»).

    The ranking uses freshness, the members the caller follows, variety of topics and what the
    caller has already reacted to, saved or commented on. It never uses religion or any personal
    detail, and the caller can switch personalisation off, which leaves freshness and variety.
    The first request pins the moment of ranking in `next_cursor`, so the next pages continue the
    same list.
    """
    page = await feed_service.for_you(db, viewer, cursors.decode(cursor), limit)
    return await _page(db, page, viewer, cursor, photos)


@router.get("/feed/latest", summary="Every public post, newest first")
async def feed_latest(
    viewer: OptionalUser,
    db: DbDep,
    photos: PhotoStoreDep,
    cursor: str | None = None,
    limit: int = Limit,
) -> FeedPage:
    """Return the public posts in the order they were published; no ranking, no personalisation."""
    page = await feed_service.latest(db, viewer, cursors.decode(cursor), limit)
    return await _page(db, page, viewer, cursor, photos)


@router.get("/u/{handle}/posts", summary="A member's published posts")
async def member_posts(
    handle: str,
    viewer: OptionalUser,
    db: DbDep,
    photos: PhotoStoreDep,
    cursor: str | None = None,
    limit: int = Limit,
) -> FeedPage:
    """
    Return a member's published posts that the caller may read, newest first.

    404 when no such member exists or a block stands between the two.
    """
    member = await member_service.visible_member(db, handle, viewer)
    page = await feed_service.by_member(db, member, viewer, cursors.decode(cursor), limit)
    return await _page(db, page, viewer, cursor, photos)
