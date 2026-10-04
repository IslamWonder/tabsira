"""
Turning posts into responses, a page at a time.

A page costs a fixed number of queries whatever its size: the like counts, the comment counts,
the viewer's own likes and bookmarks, and the scripture the publications cite. Nothing is
counted on a stored column: a count is a count of rows. A reader's response puts scripture in
by reference from the store (`evidence_view`); the author's reflection is labelled as theirs.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src import messages
from src.models.social import (
    Bookmark,
    Comment,
    CommentStatus,
    InsightPublication,
    PostLike,
    PostStatus,
)
from src.models.user import User
from src.schemas.social import (
    InsightOut,
    MemberOut,
    PostOut,
    ReflectionOut,
    ViewerPostOut,
    WhyOut,
)
from src.services.evidence_view import Evidence, load_evidence
from src.services.moderation_service import known_reason
from src.services.post_service import PostRow


def outcome_message(status: str, reason: str | None) -> str | None:
    """Say what happened to a post or a comment, in Arabic, to the person who wrote it."""
    if status == PostStatus.PENDING_REVIEW.value:
        return messages.OUTCOME_REASONS.get(reason or "", messages.OUTCOME_GUARD_UNCERTAIN)
    if status in {PostStatus.REJECTED.value, PostStatus.REMOVED.value}:
        if reason in messages.REASON_LABELS:
            return messages.OUTCOME_REJECTED.format(reason=messages.REASON_LABELS[reason])
        return messages.OUTCOME_UNKNOWN
    return None


def insight_of(publication: InsightPublication, evidence: Evidence) -> InsightOut:
    """Show the publication as a reader sees it, its scripture read from the store by reference."""
    quran = [
        evidence.quran[key]
        for ref in publication.quran_refs
        if (key := (ref["surah"], ref["ayah"])) in evidence.quran
    ]
    hadith = [
        evidence.hadith[key]
        for ref in publication.hadith_refs
        if (key := (ref["collection"], ref["number"])) in evidence.hadith
    ]
    return InsightOut(
        title=publication.title,
        glimpse=publication.glimpse,
        relation_type=publication.relation_type,
        concepts=list(publication.concepts),
        explanation=publication.explanation_excerpt,
        step=publication.step_text,
        has_photo=publication.photo_ref is not None,
        insight_version=publication.insight_version,
        quran=quran,
        hadith=hadith,
    )


async def _like_counts(db: AsyncSession, post_ids: list[int]) -> dict[int, int]:
    rows = await db.execute(
        select(PostLike.post_id, func.count())
        .where(PostLike.post_id.in_(post_ids))
        .group_by(PostLike.post_id)
    )
    return dict(rows.all())


async def _comment_counts(db: AsyncSession, post_ids: list[int]) -> dict[int, int]:
    """Count the published comments, replies included: the ones a reader can read."""
    rows = await db.execute(
        select(Comment.post_id, func.count())
        .where(Comment.post_id.in_(post_ids), Comment.status == CommentStatus.PUBLISHED)
        .group_by(Comment.post_id)
    )
    return dict(rows.all())


def _post_out(
    row: PostRow,
    publication: InsightPublication,
    *,
    evidence: Evidence,
    viewer: User | None,
    counts: tuple[dict[int, int], dict[int, int]],
    flags: tuple[set[int], set[int]],
    why: WhyOut | None,
) -> PostOut:
    post = row.post
    is_author = viewer is not None and viewer.id == post.author_id
    likes, comments = counts
    liked, saved = flags
    return PostOut(
        id=post.id,
        author=MemberOut(handle=row.author.handle or "", public_name=row.author.public_name or ""),
        insight=insight_of(publication, evidence),
        reflection=(
            ReflectionOut(
                text=post.reflection, looks_like_scripture=post.reflection_looks_like_scripture
            )
            if post.reflection
            else None
        ),
        visibility=post.visibility,
        status=post.status,
        status_reason=known_reason(post.status_reason) if is_author else None,
        status_message=outcome_message(post.status, post.status_reason) if is_author else None,
        published_at=post.published_at,
        created_at=post.created_at,
        like_count=likes.get(post.id, 0),
        comment_count=comments.get(post.id, 0),
        viewer=(
            None
            if viewer is None
            else ViewerPostOut(
                liked=post.id in liked, bookmarked=post.id in saved, is_author=is_author
            )
        ),
        why=why,
    )


async def build_posts(
    db: AsyncSession,
    rows: Sequence[PostRow],
    viewer: User | None,
    *,
    why: dict[int, WhyOut] | None = None,
) -> list[PostOut]:
    """Build the responses for a page of posts; a post without a publication is not shown."""
    shown = [row for row in rows if row.publication is not None]
    if not shown:
        return []
    post_ids = [row.post.id for row in shown]
    liked: set[int] = set()
    saved: set[int] = set()
    if viewer is not None:
        liked = set(
            await db.scalars(
                select(PostLike.post_id).where(
                    PostLike.user_id == viewer.id, PostLike.post_id.in_(post_ids)
                )
            )
        )
        saved = set(
            await db.scalars(
                select(Bookmark.post_id).where(
                    Bookmark.user_id == viewer.id, Bookmark.post_id.in_(post_ids)
                )
            )
        )
    publications = [row.publication for row in shown if row.publication is not None]
    evidence = await load_evidence(
        db,
        [(r["surah"], r["ayah"]) for p in publications for r in p.quran_refs],
        [(r["collection"], r["number"]) for p in publications for r in p.hadith_refs],
    )
    counts = (await _like_counts(db, post_ids), await _comment_counts(db, post_ids))
    return [
        _post_out(
            row,
            publication,
            evidence=evidence,
            viewer=viewer,
            counts=counts,
            flags=(liked, saved),
            why=None if why is None else why.get(row.post.id),
        )
        for row in shown
        if (publication := row.publication) is not None
    ]
