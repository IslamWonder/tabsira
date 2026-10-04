"""
Likes («أثر») and bookmarks.

Every route reads the post through `post_service`, so a reaction needs a post the caller may
read and, to be added, one that is published. A like is counted from its rows; who liked is
never listed. A bookmark is private to its owner.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from src.deps import CurrentUser, DbDep, VerifiedUser, limited, require_social
from src.schemas.social import FeedPage, PostIdPath, ReactionOut
from src.services import cursor as cursors
from src.services import feed_service, post_service, post_view, reaction_service
from src.services.social_limits import WriteKind

router = APIRouter(tags=["reactions"], dependencies=[Depends(require_social)])

PAGE_DEFAULT = 20
PAGE_MAX = 50


async def _state(db: DbDep, post_id: int, *, liked: bool) -> ReactionOut:
    return ReactionOut(liked=liked, like_count=await reaction_service.like_count(db, post_id))


@router.put(
    "/posts/{post_id}/like",
    summary="Like a post («أثر»)",
    dependencies=[limited(WriteKind.REACTION)],
)
async def like_post(post_id: PostIdPath, user: VerifiedUser, db: DbDep) -> ReactionOut:
    """Like a published post the caller may read; liking again changes nothing."""
    await post_service.get_interactable(db, post_id, user)
    await reaction_service.like(db, post_id, user)
    await db.commit()
    return await _state(db, post_id, liked=True)


@router.delete(
    "/posts/{post_id}/like",
    summary="Take back a like",
    dependencies=[limited(WriteKind.REACTION)],
)
async def unlike_post(post_id: PostIdPath, user: CurrentUser, db: DbDep) -> ReactionOut:
    """Take back the caller's like; safe to repeat."""
    await post_service.get_readable(db, post_id, user)
    await reaction_service.unlike(db, post_id, user)
    await db.commit()
    return await _state(db, post_id, liked=False)


@router.put(
    "/posts/{post_id}/bookmark",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Save a post",
    dependencies=[limited(WriteKind.REACTION)],
)
async def bookmark_post(post_id: PostIdPath, user: CurrentUser, db: DbDep) -> Response:
    """Save a published post the caller may read; saving again changes nothing."""
    await post_service.get_interactable(db, post_id, user)
    await reaction_service.bookmark(db, post_id, user)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/posts/{post_id}/bookmark",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unsave a post",
    dependencies=[limited(WriteKind.REACTION)],
)
async def unbookmark_post(post_id: PostIdPath, user: CurrentUser, db: DbDep) -> Response:
    """Unsave a post; safe to repeat. A post that is gone is already gone from the list."""
    await reaction_service.unbookmark(db, post_id, user)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/bookmarks", summary="The posts the caller saved")
async def my_bookmarks(
    user: CurrentUser,
    db: DbDep,
    cursor: str | None = None,
    limit: int = Query(PAGE_DEFAULT, ge=1, le=PAGE_MAX),
) -> FeedPage:
    """
    List what the caller saved, the latest save first, and only what they may still read.

    A post that was withdrawn, removed or hidden by a block is no longer listed.
    """
    page = await feed_service.bookmarked(db, user, cursors.decode(cursor), limit)
    items = await post_view.build_posts(db, page.rows, user)
    return FeedPage(
        items=items,
        next_cursor=page.next_cursor,
        empty_reason="no_posts" if cursor is None and not items else None,
    )
