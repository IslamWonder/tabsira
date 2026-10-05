"""Collect what an account wrote and did on the social network, for its export."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.scan import Insight
from src.models.social import (
    Block,
    Bookmark,
    Comment,
    Follow,
    InsightPublication,
    Post,
    PostReaction,
    Report,
)
from src.models.user import User
from src.schemas.social_export import (
    CommentExport,
    HandleExport,
    PostExport,
    PostMarkExport,
    PublicationExport,
    ReactionExport,
    ReportExport,
    SocialExport,
)
from src.services.moderation_service import known_reason


async def _handles(db: AsyncSession, statement: Select[str | None, datetime]) -> list[HandleExport]:
    return [
        HandleExport(handle=handle or "", since=since)
        for handle, since in await db.execute(statement)
    ]


PHOTO_FACTS = frozenset({"has_photo", "published"})


def _publication(publication: InsightPublication, copy_exists: bool | None) -> PublicationExport:
    """Return the publication for its owner, the photo as facts: the choice made, a copy existing now."""
    chosen = publication.photo_ref is not None
    columns = {
        name: getattr(publication, name)
        for name in PublicationExport.model_fields
        if name not in PHOTO_FACTS
    }
    return PublicationExport(**columns, has_photo=chosen, published=chosen and bool(copy_exists))


async def collect(db: AsyncSession, user: User) -> SocialExport:
    """Gather the user's posts, comments, follows, blocks, reactions, bookmarks and reports."""
    # The insight's public key says whether a copy exists now; the key itself never leaves.
    posts = await db.execute(
        select(Post, InsightPublication, Insight.photo_public_key.is_not(None))
        .outerjoin(InsightPublication, InsightPublication.id == Post.publication_id)
        .outerjoin(Insight, Insight.id == InsightPublication.insight_id)
        .where(Post.author_id == user.id)
        .order_by(Post.created_at, Post.id)
    )
    comments = await db.scalars(
        select(Comment).where(Comment.author_id == user.id).order_by(Comment.created_at, Comment.id)
    )
    reactions = await db.execute(
        select(PostReaction.post_id, PostReaction.kind, PostReaction.created_at)
        .where(PostReaction.user_id == user.id)
        .order_by(PostReaction.created_at, PostReaction.post_id, PostReaction.kind)
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
                    None if publication is None else _publication(publication, copy_exists)
                ),
            )
            for post, publication, copy_exists in posts
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
        reactions=[
            ReactionExport(post_id=post_id, kind=kind, at=at) for post_id, kind, at in reactions
        ],
        bookmarks=[PostMarkExport(post_id=post_id, at=at) for post_id, at in bookmarks],
        reports=[ReportExport.model_validate(report) for report in reports],
    )
