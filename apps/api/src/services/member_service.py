"""
Public profiles and follows.

A profile says a handle, a public name, the month the account joined and three counts:
published public posts, followers and accounts followed. Never an e-mail address, the
account's own name, anything from the private profile, or a place. The counts are read from
the rows they count, so they cannot drift; a block makes the other account unfindable.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors import AppError, ErrorCode
from src.models.social import Follow, Post, PostStatus, PostVisibility
from src.models.user import User
from src.schemas.social import MemberProfileOut, ViewerRelationOut
from src.services import block_service, public_identity


def not_found() -> AppError:
    return AppError(ErrorCode.NOT_FOUND, "No such member.", status_code=404)


async def visible_member(db: AsyncSession, handle: str, viewer: User | None) -> User:
    """
    Return the live account that holds `handle`, or answer 404.

    A person the viewer has blocked, or who has blocked the viewer, answers exactly as one
    who does not exist.
    """
    member = await public_identity.find_member(db, handle)
    if member is None:
        raise not_found()
    if viewer is not None and await block_service.are_blocked(db, viewer.id, member.id):
        raise not_found()
    return member


async def profile_of(db: AsyncSession, member: User, viewer: User | None) -> MemberProfileOut:
    """Build the public profile of `member` as `viewer` (a guest, or a signed-in account) sees it."""
    posts = await db.scalar(
        select(func.count())
        .select_from(Post)
        .where(
            Post.author_id == member.id,
            Post.status == PostStatus.PUBLISHED,
            Post.visibility == PostVisibility.PUBLIC,
        )
    )
    followers = await db.scalar(
        select(func.count()).select_from(Follow).where(Follow.followee_id == member.id)
    )
    following = await db.scalar(
        select(func.count()).select_from(Follow).where(Follow.follower_id == member.id)
    )
    viewer_relation = None
    if viewer is not None:
        follows = await db.scalar(
            select(Follow.follower_id).where(
                Follow.follower_id == viewer.id, Follow.followee_id == member.id
            )
        )
        viewer_relation = ViewerRelationOut(
            follows=follows is not None, is_self=viewer.id == member.id
        )
    return MemberProfileOut(
        handle=member.handle or "",
        public_name=member.public_name or "",
        joined_month=member.created_at.strftime("%Y-%m"),
        posts_count=posts or 0,
        followers_count=followers or 0,
        following_count=following or 0,
        viewer=viewer_relation,
    )


async def follow(db: AsyncSession, follower: User, target: User) -> None:
    """Follow `target`; following twice changes nothing, and nobody follows themselves."""
    if follower.id == target.id:
        raise AppError(ErrorCode.BAD_REQUEST, "You cannot follow yourself.", status_code=400)
    await db.execute(
        insert(Follow)
        .values(follower_id=follower.id, followee_id=target.id)
        .on_conflict_do_nothing(index_elements=[Follow.follower_id, Follow.followee_id])
    )


async def unfollow(db: AsyncSession, follower: User, target: User) -> None:
    """Stop following `target`; safe to repeat."""
    await db.execute(
        delete(Follow).where(Follow.follower_id == follower.id, Follow.followee_id == target.id)
    )
