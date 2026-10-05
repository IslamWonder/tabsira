"""
Turning posts into responses, a page at a time.

A page costs a fixed number of queries whatever its size: the reaction counts, the comment counts,
the viewer's own reactions and bookmarks, and the scripture the publications cite. Nothing is
counted on a stored column: a count is a count of rows. A reader's response puts scripture in
by reference from the store (`evidence_view`); the author's reflection is labelled as theirs.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.messages import messages_for
from src.models.social import (
    Bookmark,
    Comment,
    CommentStatus,
    Follow,
    InsightPublication,
    PostStatus,
    PostVisibility,
    ReactionKind,
)
from src.models.user import User
from src.schemas.geo import PublicCountryOut
from src.schemas.social import (
    InsightOut,
    PostAuthorOut,
    PostOut,
    ReactionCountsOut,
    ReflectionOut,
    ViewerPostOut,
    WhyOut,
)
from src.services import photo_service, public_identity, reaction_service
from src.services.evidence_view import Evidence, load_evidence
from src.services.moderation_service import known_reason
from src.services.post_service import PostRow
from src.storage.photos import PhotoStore


def outcome_message(status: str, reason: str | None) -> str | None:
    """Say what happened to a post or a comment, in Arabic, to the person who wrote it."""
    if status == PostStatus.PENDING_REVIEW.value:
        return messages_for().outcome_reasons.get(
            reason or "", messages_for().outcome_guard_uncertain
        )
    if status in {PostStatus.REJECTED.value, PostStatus.REMOVED.value}:
        if reason in messages_for().reason_labels:
            return messages_for().outcome_rejected.format(
                reason=messages_for().reason_labels[reason]
            )
        return messages_for().outcome_unknown
    return None


def insight_of(
    publication: InsightPublication, evidence: Evidence, *, photo_url: str | None = None
) -> InsightOut:
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
        photo_url=photo_url,
        insight_version=publication.insight_version,
        quran=quran,
        hadith=hadith,
    )


async def _comment_counts(db: AsyncSession, post_ids: list[int]) -> dict[int, int]:
    """Count the published comments, replies included: the ones a reader can read."""
    rows = await db.execute(
        select(Comment.post_id, func.count())
        .where(Comment.post_id.in_(post_ids), Comment.status == CommentStatus.PUBLISHED)
        .group_by(Comment.post_id)
    )
    return dict(rows.all())


def _shows_photo_publicly(row: PostRow, publication: InsightPublication) -> bool:
    """Only a published public post that asked for the photo gives its public address away."""
    return (
        publication.photo_ref is not None
        and row.post.status is PostStatus.PUBLISHED
        and row.post.visibility is PostVisibility.PUBLIC
    )


def _post_out(
    row: PostRow,
    publication: InsightPublication,
    *,
    evidence: Evidence,
    photo_urls: dict[int, str],
    viewer: User | None,
    counts: tuple[dict[int, ReactionCountsOut], dict[int, int]],
    flags: tuple[dict[int, list[ReactionKind]], set[int], set[uuid.UUID]],
    countries: dict[uuid.UUID, PublicCountryOut],
    why: WhyOut | None,
) -> PostOut:
    post = row.post
    photo_url = (
        photo_urls.get(publication.insight_id) if _shows_photo_publicly(row, publication) else None
    )
    is_author = viewer is not None and viewer.id == post.author_id
    reactions, comments = counts
    given, saved, followed = flags
    return PostOut(
        id=post.id,
        author=PostAuthorOut(
            handle=row.author.handle or "",
            public_name=public_identity.shown_name(row.author),
            country=countries.get(post.author_id),
        ),
        insight=insight_of(publication, evidence, photo_url=photo_url),
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
        reactions=reactions.get(post.id, reaction_service.counts_of({})),
        comment_count=comments.get(post.id, 0),
        viewer=(
            None
            if viewer is None
            else ViewerPostOut(
                reactions=given.get(post.id, []),
                bookmarked=post.id in saved,
                is_author=is_author,
                follows_author=post.author_id in followed,
            )
        ),
        why=why,
    )


async def build_posts(
    db: AsyncSession,
    rows: Sequence[PostRow],
    viewer: User | None,
    *,
    photos: PhotoStore,
    why: dict[int, WhyOut] | None = None,
) -> list[PostOut]:
    """
    Build the responses for a page of posts; a post without a publication is not shown.

    `photos` gives the address of a photo's public copy (v2 §19), carried only by a published
    public post whose owner chose the photo and whose copy exists now.
    """
    shown = [row for row in rows if row.publication is not None]
    if not shown:
        return []
    post_ids = [row.post.id for row in shown]
    given: dict[int, list[ReactionKind]] = {}
    saved: set[int] = set()
    followed: set[uuid.UUID] = set()
    if viewer is not None:
        given = await reaction_service.mine(db, post_ids, viewer)
        saved = set(
            await db.scalars(
                select(Bookmark.post_id).where(
                    Bookmark.user_id == viewer.id, Bookmark.post_id.in_(post_ids)
                )
            )
        )
        # Which authors of the page the reader follows, in one query, so each card can offer it.
        followed = set(
            await db.scalars(
                select(Follow.followee_id).where(
                    Follow.follower_id == viewer.id,
                    Follow.followee_id.in_({row.post.author_id for row in shown}),
                )
            )
        )
    publications = [row.publication for row in shown if row.publication is not None]
    evidence = await load_evidence(
        db,
        [(r["surah"], r["ayah"]) for p in publications for r in p.quran_refs],
        [(r["collection"], r["number"]) for p in publications for r in p.hadith_refs],
    )
    counts = (await reaction_service.counts(db, post_ids), await _comment_counts(db, post_ids))
    countries = await public_identity.shown_countries(db, {row.post.author_id for row in shown})
    photo_urls = await photo_service.public_urls(
        db,
        photos,
        {
            publication.insight_id
            for row in shown
            if (publication := row.publication) is not None
            and _shows_photo_publicly(row, publication)
        },
    )
    return [
        _post_out(
            row,
            publication,
            evidence=evidence,
            photo_urls=photo_urls,
            viewer=viewer,
            counts=counts,
            flags=(given, saved, followed),
            countries=countries,
            why=None if why is None else why.get(row.post.id),
        )
        for row in shown
        if (publication := row.publication) is not None
    ]
