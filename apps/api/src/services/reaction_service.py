"""
Likes («أثر») and bookmarks: one per account and post, safe to repeat.

A like is counted from its rows and shown as a number; who liked is never listed. A bookmark is
private: nobody sees whose it is, and nobody counts it. Neither is a counter on the post, so
neither can drift.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.social import Bookmark, PostLike
from src.models.user import User


async def like_count(db: AsyncSession, post_id: int) -> int:
    count = await db.scalar(
        select(func.count()).select_from(PostLike).where(PostLike.post_id == post_id)
    )
    return count or 0


async def like(db: AsyncSession, post_id: int, user: User) -> None:
    """Add the caller's like; liking again changes nothing."""
    await db.execute(
        insert(PostLike)
        .values(post_id=post_id, user_id=user.id)
        .on_conflict_do_nothing(index_elements=[PostLike.post_id, PostLike.user_id])
    )


async def unlike(db: AsyncSession, post_id: int, user: User) -> None:
    await db.execute(
        delete(PostLike).where(PostLike.post_id == post_id, PostLike.user_id == user.id)
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
