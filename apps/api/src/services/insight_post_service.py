"""
The post an insight is published as in «تبصرة تواصل», made once (owners' decision 68).

Publishing a basira puts it in the author's publications by default: sharing it, placing it on
the atlas or publishing it here all lead to one post. `ensure_post` is that step, and it is
idempotent: an insight that already has a live post (a draft is submitted, anything else is
returned as it is) gets no second one. A post the author withdrew leaves no link to its insight,
so a new one can be made after it; one a moderator removed or the guard refused is returned, never
replaced, so publishing again never steps around a decision.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings
from src.models.social import InsightPublication, Post, PostStatus, PostVisibility
from src.models.user import User
from src.services import post_service, publication_service
from src.services.insight_source import InsightSource
from src.services.moderation_guard import TextGuard
from src.services.post_service import PostRow
from src.storage.photos import PhotoStore


async def live_post(db: AsyncSession, author: User, insight_id: int) -> PostRow | None:
    """Return the author's newest post of this insight that still holds its publication."""
    found = (
        await db.execute(
            select(Post, InsightPublication)
            .join(InsightPublication, Post.publication_id == InsightPublication.id)
            .where(Post.author_id == author.id, InsightPublication.insight_id == insight_id)
            .order_by(Post.created_at.desc(), Post.id.desc())
            .limit(1)
        )
    ).first()
    return None if found is None else PostRow(found[0], found[1], author)


async def ensure_post(
    db: AsyncSession,
    source: InsightSource,
    author: User,
    insight_id: int,
    settings: Settings,
    guard: TextGuard,
    photos: PhotoStore,
    *,
    publish_photo: bool = False,
) -> PostRow:
    """
    Return the insight's post, publishing a new public one with no reflection when it has none.

    A new post goes through the guard like any other (with no text of the author's, the guard
    has nothing to judge and it is published); `publish_photo` is the owner's choice to show the
    kept photo, checked against the photo rules by `publication_service`.
    """
    found = await live_post(db, author, insight_id)
    if found is not None:
        if found.post.status is PostStatus.DRAFT:
            await post_service.submit(db, found, guard, photos=photos)
        return found
    publication = await publication_service.create_publication(
        db, source, author, insight_id, settings, publish_photo=publish_photo
    )
    post = post_service.create_draft(db, author, publication, None, PostVisibility.PUBLIC)
    await db.flush()
    row = PostRow(post, publication, author)
    await post_service.submit(db, row, guard, photos=photos)
    return row
