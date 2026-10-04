"""Collect what an account wrote and did on the social network, for its export."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.social import (
    Block,
    Bookmark,
    Comment,
    Follow,
    InsightPublication,
    Post,
    PostLike,
    Report,
)
from src.models.user import User
from src.schemas.social_export import (
    CommentExport,
    HandleExport,
    PostExport,
    PostMarkExport,
    PublicationExport,
    ReportExport,
    SocialExport,
)
from src.services.moderation_service import known_reason


async def _handles(db: AsyncSession, statement: Select[str | None, datetime]) -> list[HandleExport]:
    return [
        HandleExport(handle=handle or "", since=since)
        for handle, since in await db.execute(statement)
    ]


async def collect(db: AsyncSession, user: User) -> SocialExport:
    """Gather the user's posts, comments, follows, blocks, likes, bookmarks and reports."""
    posts = await db.execute(
        select(Post, InsightPublication)
        .outerjoin(InsightPublication, InsightPublication.id == Post.publication_id)
        .where(Post.author_id == user.id)
        .order_by(Post.created_at, Post.id)
    )
    comments = await db.scalars(
        select(Comment).where(Comment.author_id == user.id).order_by(Comment.created_at, Comment.id)
    )
    likes = await db.execute(
        select(PostLike.post_id, PostLike.created_at)
        .where(PostLike.user_id == user.id)
        .order_by(PostLike.created_at, PostLike.post_id)
    )
    bookmarks = await db.execute(
        select(Bookmark.post_id, Bookmark.created_at)
        .where(Bookmark.user_id == user.id)
        .order_by(Bookmark.created_at, Bookmark.post_id)
    )
    reports = await db.scalars(
        select(Report).where(Report.reporter_id == user.id).order_by(Report.created_at, Report.id)
    )
    return SocialExport(
        posts=[
            PostExport(
                id=post.id,
                status=post.status,
                status_reason=known_reason(post.status_reason),
                visibility=post.visibility,
                reflection=post.reflection,
                created_at=post.created_at,
                submitted_at=post.submitted_at,
                published_at=post.published_at,
                removed_at=post.removed_at,
                removal_source=post.removal_source,
                publication=(
                    None if publication is None else PublicationExport.model_validate(publication)
                ),
            )
            for post, publication in posts
        ],
        comments=[
            CommentExport(
                id=comment.id,
                post_id=comment.post_id,
                parent_id=comment.parent_id,
                body=comment.body,
                status=comment.status,
                status_reason=known_reason(comment.status_reason),
                created_at=comment.created_at,
            )
            for comment in comments
        ],
        following=await _handles(
            db,
            select(User.handle, Follow.created_at)
            .join(Follow, Follow.followee_id == User.id)
            .where(Follow.follower_id == user.id, User.handle.is_not(None))
            .order_by(Follow.created_at.desc(), User.id),
        ),
        blocked=await _handles(
            db,
            select(User.handle, Block.created_at)
            .join(Block, Block.blocked_id == User.id)
            .where(Block.blocker_id == user.id, User.handle.is_not(None))
            .order_by(Block.created_at.desc(), User.id),
        ),
        likes=[PostMarkExport(post_id=post_id, at=at) for post_id, at in likes],
        bookmarks=[PostMarkExport(post_id=post_id, at=at) for post_id, at in bookmarks],
        reports=[ReportExport.model_validate(report) for report in reports],
    )
