"""
Posts: who may see one, how one is made, edited, submitted and withdrawn.

`check_access` is the one place that decides whether a viewer may read a post, and it
answers the same way for a post that does not exist, one in a state its viewer may not see,
one behind a block and one for followers the viewer does not follow: 404. Only a post that
was published and then taken down answers 410 Gone, and only to someone who could have read
it. Knowing a post's id grants nothing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock
from src.errors import AppError, ErrorCode
from src.models.moderation import ModerationActionKind, ModerationSource
from src.models.social import (
    Bookmark,
    Comment,
    Follow,
    InsightPublication,
    Post,
    PostReaction,
    PostStatus,
    PostVisibility,
    RemovalSource,
)
from src.models.user import User
from src.pipeline.leak_guard import LeakGuard
from src.services import block_service, moderation_service, photo_service
from src.services.moderation_guard import NO_TEXT, TextGuard
from src.storage.photos import PhotoStore

_LEAK_GUARD = LeakGuard()

type Lock = Literal["update", "share"]


@dataclass(frozen=True)
class PostRow:
    """A post with its publication and its author, loaded together."""

    post: Post
    publication: InsightPublication | None
    author: User


def not_found() -> AppError:
    return AppError(ErrorCode.NOT_FOUND, "No such post.", status_code=404)


def gone() -> AppError:
    return AppError(ErrorCode.GONE, "This post is gone.", status_code=410)


async def load_row(db: AsyncSession, post_id: int, *, lock: Lock | None = None) -> PostRow | None:
    """
    Load a post, its publication and its author, whatever its state.

    `lock` takes a row lock on the post until the transaction ends, and reads it fresh. A write
    that depends on the post's state (an edit, a submission, a withdrawal) takes `"update"`, so
    two of them never interleave; a write that adds something to the post (a reaction, a comment, a
    report) takes `"share"`, so it either lands before a withdrawal and is erased by it, or
    waits for it and finds the post gone.
    """
    statement = (
        select(Post, InsightPublication, User)
        .join(User, User.id == Post.author_id)
        .outerjoin(InsightPublication, InsightPublication.id == Post.publication_id)
        .where(Post.id == post_id)
    )
    if lock is not None:
        statement = statement.with_for_update(read=lock == "share", of=Post).execution_options(
            populate_existing=True
        )
    found = (await db.execute(statement)).one_or_none()
    return None if found is None else PostRow(*found)


async def _follows(db: AsyncSession, viewer: User, author_id: uuid.UUID) -> bool:
    found = await db.scalar(
        select(Follow.follower_id).where(
            Follow.follower_id == viewer.id, Follow.followee_id == author_id
        )
    )
    return found is not None


async def check_access(db: AsyncSession, row: PostRow, viewer: User | None) -> None:
    """Raise 404 or 410 unless `viewer` (None for a guest) may read this post."""
    post, author = row.post, row.author
    if not author.is_active or author.deleted_at is not None:
        raise not_found()
    is_author = viewer is not None and viewer.id == post.author_id
    if (
        viewer is not None
        and not is_author
        and await block_service.are_blocked(db, viewer.id, author.id)
    ):
        raise not_found()
    if not is_author:
        if post.status not in {PostStatus.PUBLISHED, PostStatus.REMOVED}:
            raise not_found()
        # Only what was public can be gone: a draft, or a post held or refused and then removed,
        # was never seen by anyone else, and its id must not say that it once existed.
        if post.published_at is None:
            raise not_found()
        if post.visibility is PostVisibility.FOLLOWERS and not (
            viewer is not None and await _follows(db, viewer, post.author_id)
        ):
            raise not_found()
    if post.status is PostStatus.REMOVED or row.publication is None:
        raise gone()


async def get_readable(
    db: AsyncSession, post_id: int, viewer: User | None, *, lock: Lock | None = None
) -> PostRow:
    """Load a post `viewer` may read, or raise 404 or 410."""
    row = await load_row(db, post_id, lock=lock)
    if row is None:
        raise not_found()
    await check_access(db, row, viewer)
    return row


async def get_interactable(db: AsyncSession, post_id: int, viewer: User) -> PostRow:
    """Load a post `viewer` may react to, save, comment on or report: readable, and published."""
    row = await get_readable(db, post_id, viewer, lock="share")
    if row.post.status is not PostStatus.PUBLISHED:
        raise AppError(ErrorCode.CONFLICT, "This post is not published.", status_code=409)
    return row


async def get_owned(db: AsyncSession, post_id: int, user: User) -> PostRow:
    """Load and lock one of the caller's own posts; someone else's is a 404."""
    row = await load_row(db, post_id, lock="update")
    if row is None or row.post.author_id != user.id:
        raise not_found()
    if row.post.status is PostStatus.REMOVED or row.publication is None:
        raise gone()
    return row


# ─── Writing ───────────────────────────────────────────────────────────────────


def looks_like_scripture(reflection: str | None) -> bool:
    """Whether the author's own words read like Quran or hadith (they are still only theirs)."""
    return reflection is not None and _LEAK_GUARD.check(reflection).leaked


def create_draft(
    db: AsyncSession,
    author: User,
    publication: InsightPublication,
    reflection: str | None,
    visibility: PostVisibility,
) -> Post:
    """Start a draft of a publication; nothing is visible to anyone else until it is submitted."""
    post = Post(
        author_id=author.id,
        publication_id=publication.id,
        reflection=reflection,
        reflection_looks_like_scripture=looks_like_scripture(reflection),
        visibility=visibility,
    )
    db.add(post)
    return post


def _not_editable() -> AppError:
    return AppError(
        ErrorCode.CONFLICT, "Only a draft or a refused post can be edited.", status_code=409
    )


def update_draft(
    post: Post, *, reflection: str | None, visibility: PostVisibility | None, reflection_given: bool
) -> None:
    """
    Change a draft or a refused post; a refused one becomes a draft again, to be resubmitted.

    A post that is waiting for review or is published cannot be edited: what a moderator or the
    guard judged is what stays.
    """
    if post.status not in {PostStatus.DRAFT, PostStatus.REJECTED}:
        raise _not_editable()
    if reflection_given:
        post.reflection = reflection
        post.reflection_looks_like_scripture = looks_like_scripture(reflection)
    if visibility is not None:
        post.visibility = visibility
    post.status = PostStatus.DRAFT
    post.status_reason = None


async def submit(db: AsyncSession, row: PostRow, guard: TextGuard, *, photos: PhotoStore) -> Post:
    """
    Run a draft through the guard and settle it: published, refused with a reason, or held.

    The guard is a network call, so the transaction is committed before it and the post is
    locked and re-read after it: a draft edited or submitted twice in the meantime is refused
    rather than settled on a verdict about other words. A published post that shows the photo
    gets its public copy made now (`photo_service`), under the photo rules checked again.
    """
    post = row.post
    if post.status is not PostStatus.DRAFT:
        raise AppError(ErrorCode.CONFLICT, "Only a draft can be submitted.", status_code=409)
    text = post.reflection
    post_id = post.id
    await db.commit()
    verdict = await guard.check(text) if text else NO_TEXT
    locked = (
        await db.execute(
            select(Post)
            .where(Post.id == post_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    if locked.status is not PostStatus.DRAFT or locked.reflection != text:
        raise AppError(
            ErrorCode.CONFLICT, "The post changed while it was reviewed.", status_code=409
        )
    locked.submitted_at = clock.utcnow()
    moderation_service.settle(db, locked, verdict)
    settled: PostStatus = locked.status
    if settled is PostStatus.PUBLISHED:
        await _sync_photo(db, row.publication, photos)
    return locked


async def _sync_photo(
    db: AsyncSession, publication: InsightPublication | None, photos: PhotoStore
) -> None:
    """Bring the public copy of the photo in line with the post's state, when it shows one."""
    if publication is not None and publication.photo_ref is not None:
        await photo_service.sync_public_copy(db, photos, publication.insight_id)


async def withdraw(db: AsyncSession, row: PostRow, *, photos: PhotoStore) -> None:
    """
    Take a post back: its address answers 410, every feed drops it, and its content is erased.

    The reflection, the publication, the comments, the reactions and the bookmarks go, and so does
    the public copy of the photo unless another live publication still shows it; what stays
    is the tombstone that makes the address answer 410, and the moderation log, which holds
    no text. A draft goes the same way, so it needs no special case.
    """
    post = row.post
    now = clock.utcnow()
    await db.execute(delete(Comment).where(Comment.post_id == post.id))
    await db.execute(delete(PostReaction).where(PostReaction.post_id == post.id))
    await db.execute(delete(Bookmark).where(Bookmark.post_id == post.id))
    post.reflection = None
    post.reflection_looks_like_scripture = False
    post.status = PostStatus.REMOVED
    post.status_reason = None
    post.removal_source = RemovalSource.OWNER
    post.removed_at = now
    publication_id, post.publication_id = post.publication_id, None
    moderation_service.log_action(db, post, ModerationActionKind.WITHDRAWN, ModerationSource.OWNER)
    await db.flush()
    # After the post stops pointing at it, so the foreign key has nothing left to set to NULL.
    await db.execute(delete(InsightPublication).where(InsightPublication.id == publication_id))
    await _sync_photo(db, row.publication, photos)
