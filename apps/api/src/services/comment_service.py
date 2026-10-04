"""
Comments: who may see one, how one is written, judged and deleted.

A thread is one level deep: a comment on a post, and replies to that comment. A new comment is
`pending_review` until the guard has judged its text: published, refused with a reason, or held
for a moderator, and only its author sees it until then. `visible_comment` is the one rule for
who may read a comment, and a block hides in both directions: a comment by someone the viewer
blocked, or who blocked the viewer, is gone from the viewer's thread, and a comment by someone
the post's own author has blocked is gone for everyone. Hidden, not deleted: an unblock brings
it back.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import ColumnElement, delete, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors import AppError, ErrorCode
from src.models.social import Block, Comment, CommentStatus, Post
from src.models.user import User
from src.services import cursor as cursors
from src.services import moderation_service
from src.services.block_service import blocked_with
from src.services.moderation_guard import TextGuard

# Replies one comment may take. A bound, so a thread is a page and not an unbounded list.
MAX_REPLIES = 50


@dataclass(frozen=True)
class Thread:
    """A comment with its author and its replies, each reply with its author."""

    comment: Comment
    author: User
    replies: list[tuple[Comment, User]]


def not_found() -> AppError:
    return AppError(ErrorCode.NOT_FOUND, "No such comment.", status_code=404)


def visible_comment(viewer: User | None) -> ColumnElement[bool]:
    """
    Match the comments `viewer` (None for a guest) may read.

    Published ones, and the viewer's own whatever their state, minus every comment by someone
    the viewer has blocked or who has blocked them, and every comment by someone the post's
    author has blocked.
    """
    published = Comment.status == CommentStatus.PUBLISHED
    shown = published if viewer is None else published | (Comment.author_id == viewer.id)
    blocked_by_post_author = (
        select(Block.blocker_id)
        .join(Post, Post.author_id == Block.blocker_id)
        .where(Post.id == Comment.post_id, Block.blocked_id == Comment.author_id)
        .exists()
    )
    visible = shown & ~blocked_by_post_author
    if viewer is not None:
        visible = visible & Comment.author_id.not_in(blocked_with(viewer.id))
    return visible


def _live_author() -> ColumnElement[bool]:
    return User.is_active.is_(True) & User.deleted_at.is_(None) & User.handle.is_not(None)


async def get_visible(
    db: AsyncSession, post_id: int, comment_id: int, viewer: User | None
) -> tuple[Comment, User]:
    """Load a comment of this post that `viewer` may read, or raise 404."""
    found = (
        await db.execute(
            select(Comment, User)
            .join(User, User.id == Comment.author_id)
            .where(
                Comment.id == comment_id,
                Comment.post_id == post_id,
                visible_comment(viewer),
                _live_author(),
            )
        )
    ).one_or_none()
    if found is None:
        raise not_found()
    return found[0], found[1]


async def list_threads(
    db: AsyncSession,
    post_id: int,
    viewer: User | None,
    cursor: cursors.Cursor | None,
    limit: int,
) -> tuple[list[Thread], str | None]:
    """List a post's comments oldest first with their replies, and the cursor of the next page."""
    statement = (
        select(Comment, User)
        .join(User, User.id == Comment.author_id)
        .where(
            Comment.post_id == post_id,
            Comment.parent_id.is_(None),
            visible_comment(viewer),
            _live_author(),
        )
        .order_by(Comment.created_at, Comment.id)
        .limit(limit + 1)
    )
    if cursor is not None:
        statement = statement.where(
            tuple_(Comment.created_at, Comment.id) > tuple_(cursor.at, cursor.id)
        )
    found = (await db.execute(statement)).all()
    tops = found[:limit]
    replies: defaultdict[int | None, list[tuple[Comment, User]]] = defaultdict(list)
    if tops:
        rows = await db.execute(
            select(Comment, User)
            .join(User, User.id == Comment.author_id)
            .where(
                Comment.parent_id.in_([comment.id for comment, _ in tops]),
                visible_comment(viewer),
                _live_author(),
            )
            .order_by(Comment.created_at, Comment.id)
        )
        for reply, author in rows:
            replies[reply.parent_id].append((reply, author))
    threads = [Thread(comment, author, replies[comment.id]) for comment, author in tops]
    next_cursor = None
    if len(found) > limit:
        last = tops[-1][0]
        next_cursor = cursors.encode(cursors.Cursor(at=last.created_at, id=last.id))
    return threads, next_cursor


async def create_comment(
    db: AsyncSession, post: Post, author: User, body: str, parent_id: int | None
) -> Comment:
    """
    Add a comment, or a reply, in review.

    A reply must answer a comment of this post that the author may read and that is not itself
    a reply, and a comment takes at most `MAX_REPLIES`.
    """
    if parent_id is not None:
        parent, _ = await get_visible(db, post.id, parent_id, author)
        if parent.parent_id is not None:
            raise AppError(
                ErrorCode.CONFLICT,
                "A reply cannot be answered: threads are one level deep.",
                status_code=409,
            )
        taken = await db.scalar(
            select(func.count()).select_from(Comment).where(Comment.parent_id == parent.id)
        )
        if (taken or 0) >= MAX_REPLIES:
            raise AppError(
                ErrorCode.CONFLICT, "This comment has too many replies.", status_code=409
            )
    comment = Comment(post_id=post.id, author_id=author.id, parent_id=parent_id, body=body)
    db.add(comment)
    await db.flush()
    return comment


async def judge(db: AsyncSession, comment: Comment, guard: TextGuard) -> Comment:
    """
    Run a new comment through the guard and settle it.

    The guard is a network call, so the transaction is committed before it and the comment is
    locked and re-read after it. A comment deleted in the meantime ends the call with a 404.
    """
    comment_id, body = comment.id, comment.body
    await db.commit()
    verdict = await guard.check(body)
    locked = (
        await db.execute(
            select(Comment)
            .where(Comment.id == comment_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if locked is None:
        raise not_found()
    moderation_service.settle(db, locked, verdict)
    return locked


async def delete_comment(db: AsyncSession, comment: Comment) -> None:
    """Delete a comment; its replies, which only answer it, go with it."""
    await db.execute(delete(Comment).where(Comment.id == comment.id))
