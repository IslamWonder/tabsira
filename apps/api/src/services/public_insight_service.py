"""
Publishing an insight, withdrawing it, and reading a published one as a stranger.

Publishing is the owner's own act and needs a signed-in, verified account (decision 25); a
guest's insight is never public. Whether it may be public is decided here, whatever the caller
says: it must carry at least one text shown from the store (a verse, or a hadith whose ruling
allows it), none of its platform text may look like scripture, and its scene must not be
sensitive. A public insight names no photo, no scan, no place and no exact point, and says
about its owner only the handle and public name they chose.

Reading answers 404 for an insight that is not public, withdrawn, or whose owner's account is
closed, the same answer as for one that does not exist.
"""

from __future__ import annotations

from typing import NoReturn

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock, messages
from src.errors import AppError, ErrorCode
from src.models import Insight, Scan
from src.models.user import User
from src.owner import INSIGHT, not_found
from src.pipeline.engine import RelationType
from src.pipeline.leak_guard import LeakGuard
from src.schemas.insight import (
    InsightHadith,
    InsightQuran,
    PublicationOut,
    PublicAuthorOut,
    PublicInsightOut,
)
from src.services import insight_view

_LEAK_GUARD = LeakGuard()


def _refuse(why: str) -> NoReturn:
    message = f"This insight cannot be made public: {why}."
    raise AppError(ErrorCode.INSIGHT_NOT_PUBLISHABLE, message, status_code=409)


def page_path(insight: Insight) -> str:
    """Return the path of the insight's public page on the web app."""
    return f"/insights/{insight.id}"


def state(insight: Insight) -> PublicationOut:
    """Return whether the insight is public now."""
    public = insight.published_at is not None
    return PublicationOut(
        insight_id=insight.id,
        published=public,
        published_at=insight.published_at,
        path=page_path(insight) if public else None,
    )


async def _check(db: AsyncSession, insight: Insight) -> None:
    """Refuse an insight that may not be public."""
    if insight.scan_id is not None:
        scan = await db.get(Scan, insight.scan_id)
        if scan is not None and scan.sensitive:
            _refuse("its scene is sensitive")
    verse, hadith, _awaiting = await insight_view.shown_evidence(db, insight)
    if verse is None and hadith is None:
        _refuse("it has no text to show from the store")
    texts = {"title": insight.title, "glimpse": insight.glimpse}
    texts |= {f"explanation {n}": str(part["text"]) for n, part in enumerate(insight.explanation)}
    if insight.small_step:
        texts["step"] = str(insight.small_step["text"])
    if any(_LEAK_GUARD.check(text).leaked for text in texts.values()):
        _refuse("its text looks like scripture, which only the store may supply")


async def publish(db: AsyncSession, insight: Insight) -> PublicationOut:
    """Make the owner's insight public; asking again changes nothing."""
    if insight.published_at is None:
        await _check(db, insight)
        insight.published_at = clock.utcnow()
        insight.withdrawn_at = None
        await db.commit()
    return state(insight)


async def withdraw(db: AsyncSession, insight: Insight) -> PublicationOut:
    """Take the insight down at once; asking again changes nothing."""
    if insight.published_at is not None:
        insight.published_at = None
        insight.withdrawn_at = clock.utcnow()
        await db.commit()
    return state(insight)


async def read_public(db: AsyncSession, insight_id: int) -> PublicInsightOut:
    """Return a published insight for a stranger, or the 404 of one that does not exist."""
    row = (
        await db.execute(
            select(Insight, User)
            .join(User, User.id == Insight.user_id)
            .where(
                Insight.id == insight_id,
                Insight.published_at.is_not(None),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
    ).first()
    if row is None:
        raise not_found(INSIGHT)
    insight, owner = row[0], row[1]
    verse, hadith, awaiting = await insight_view.shown_evidence(db, insight)
    return PublicInsightOut(
        id=insight.id,
        engine=insight.engine,
        label=insight_view.label_of(insight),
        title=insight.title,
        glimpse=insight.glimpse,
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
        hadith_status="shown" if hadith else "awaiting_verification" if awaiting else "none",
        notice=messages.HADITH_AWAITS_VERIFICATION if awaiting else None,
        pair_complete=verse is not None and hadith is not None,
        explanation_tag=messages.EXPLANATION_TAG,
        explanation=insight_view.explanation_out(insight.explanation, verse, hadith),
        small_step=insight_view.step_out(insight.small_step, verse, hadith),
        author=PublicAuthorOut(handle=owner.handle, public_name=owner.public_name)
        if owner.handle is not None and owner.public_name is not None
        else None,
        published_at=insight.published_at,
        disclosure=messages.AI_DISCLOSURE,
    )
