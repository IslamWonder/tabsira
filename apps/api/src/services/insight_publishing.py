"""
An insight made public by its owner (v2 §18), and what a stranger reads of it.

Publishing changes nothing in the insight but `published_at`; withdrawing («إلغاء
النشر») clears it, and the public address then answers like one that never
existed. Only a saved insight of a signed-in, verified account can be published
(decision 25), never by an account that declared an age under 13 (v2 §5), only
once at least one of its texts is verified and shown, never one of the declared
simulation, and never one written for its owner in person. The public view carries the texts shown,
read from the store by reference, and the platform's own words; never the
owner's profile, chat, learning history, scan, place or photo, and of the owner
only the name they chose for the public.
"""

from __future__ import annotations

from typing import NoReturn

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock, messages
from src.errors import AppError, ErrorCode
from src.models import AgeRange, Insight, Profile, User
from src.pipeline.engine import RelationType
from src.pipeline.leak_guard import LeakGuard
from src.schemas.insight import (
    InsightHadith,
    InsightQuran,
    PublicationOut,
    PublicAuthorOut,
    PublicInsightOut,
    PublicWhyOut,
)
from src.scripture.overlap import repeats_store
from src.services import insight_view

# The platform's words are checked once more at publish time: a text that reads like
# scripture never reaches a public page from anywhere but the store.
_LEAK_GUARD = LeakGuard()

# A declared simulation is never presented as live analysis (AGENTS.md).
SIMULATION_ENGINE = "demo"


def _refuse(why: str) -> NoReturn:
    message = f"This insight cannot be published: {why}."
    raise AppError(ErrorCode.INSIGHT_NOT_PUBLISHABLE, message, status_code=409)


# An account that declared an age under 13 has no public publishing (v2 §5).
_UNDER_13 = exists().where(Profile.user_id == User.id, Profile.age_range == AgeRange.UNDER_13)


def _texts(insight: Insight) -> list[str]:
    """Return every platform-written text a public page would print (as `accept.insight_texts`)."""
    texts = [insight.title, insight.glimpse]
    texts.extend(str(part.get("text", "")) for part in insight.explanation)
    texts.extend(str(clue) for clue in insight.why.get("visible_clues", []))
    texts.extend(str(limit) for limit in insight.why.get("limits", []))
    texts.append(str(insight.why.get("concept", "")))
    if insight.small_step:
        texts.append(str(insight.small_step.get("text", "")))
    texts.extend(
        str(evidence.get("matched_on", ""))
        for evidence in (insight.quran_evidence, insight.hadith_evidence)
        if evidence
    )
    return texts


async def _declared_under_13(db: AsyncSession, user_id: object) -> bool:
    age = await db.scalar(select(Profile.age_range).where(Profile.user_id == user_id))
    return age is AgeRange.UNDER_13


async def publish(db: AsyncSession, insight: Insight) -> PublicationOut:
    """Make the owner's insight public, or refuse with the reason; a second call changes nothing."""
    if insight.published_at is not None:
        return insight_view.publication_out(insight)
    if await _declared_under_13(db, insight.user_id):
        _refuse("its owner declared an age under 13, who has no public publishing")
    if insight.engine == SIMULATION_ENGINE:
        _refuse("it comes from the declared simulation, not from an analysis")
    if insight.why.get("personalised_because"):
        _refuse("it was written for its owner in person")
    verse, hadith, _awaiting = await insight_view.shown_evidence(db, insight)
    if verse is None and hadith is None:
        _refuse("none of its texts is verified and shown yet")
    texts = _texts(insight)
    # The form of scripture, and a plain copy of a stored text too (as the accept stage checks).
    if any(_LEAK_GUARD.check(text).leaked for text in texts) or await repeats_store(db, texts):
        _refuse("its text looks like scripture, which only the store may supply")
    insight.published_at = clock.utcnow()
    await db.commit()
    return insight_view.publication_out(insight)


async def withdraw(db: AsyncSession, insight: Insight) -> PublicationOut:
    """«إلغاء النشر»: take the insight off its public address; already private is fine."""
    if insight.published_at is not None:
        insight.published_at = None
        await db.commit()
    return insight_view.publication_out(insight)


async def published(db: AsyncSession, insight_id: int) -> tuple[Insight, User] | None:
    """Return a published insight and its owner, when the owner's account is live and not under 13."""
    row = (
        await db.execute(
            select(Insight, User)
            .join(User, User.id == Insight.user_id)
            .where(
                Insight.id == insight_id,
                Insight.published_at.is_not(None),
                # A second line behind `publish`: a simulation is never a public page.
                Insight.engine != SIMULATION_ENGINE,
                User.is_active,
                User.deleted_at.is_(None),
                ~_UNDER_13,
            )
        )
    ).first()
    return (row[0], row[1]) if row is not None else None


async def describe(db: AsyncSession, insight: Insight, owner: User) -> PublicInsightOut | None:
    """Return the public view, or None when no text of the insight is shown any more."""
    verse, hadith, _awaiting = await insight_view.shown_evidence(db, insight)
    if verse is None and hadith is None:
        return None
    published_at = insight.published_at
    assert published_at is not None
    return PublicInsightOut(
        id=insight.id,
        path=insight_view.public_path(insight.id),
        title=insight.title,
        glimpse=insight.glimpse,
        label=insight_view.engine_label(insight),
        relation=RelationType(insight.relation),
        relation_label=messages.RELATION_LABELS[insight.relation],
        quran=InsightQuran(
            tag=messages.QURAN_TAG,
            verse=verse,
            why=insight_view.evidence_why(insight.quran_evidence),
        )
        if verse
        else None,
        hadith=InsightHadith(
            tag=messages.SUNNAH_TAG,
            hadith=hadith,
            why=insight_view.evidence_why(insight.hadith_evidence),
        )
        if hadith
        else None,
        explanation_tag=messages.EXPLANATION_TAG,
        explanation=insight_view.explanation_out(insight.explanation, verse, hadith),
        why=PublicWhyOut(
            visible_clues=list(insight.why.get("visible_clues", [])),
            concept=str(insight.why.get("concept", "")),
            limits=list(insight.why.get("limits", [])),
        ),
        small_step=insight_view.step_out(insight.small_step, verse, hadith),
        author=PublicAuthorOut(public_name=owner.public_name) if owner.public_name else None,
        published_at=published_at,
        disclosure=messages.AI_DISCLOSURE,
    )
