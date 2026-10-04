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

from src import clock
from src.messages import messages_for
from src.errors import AppError, ErrorCode
from src.models import Insight, Scan
from src.models.user import User
from src.owner import INSIGHT, not_found
from src.pipeline.engine import RelationType
from src.scans import accept
from src.services.insight_table_source import PUBLISHABLE_ENGINE
from src.schemas.insight import (
    PublicationOut,
    PublicAuthorOut,
    PublicInsightOut,
)
from src.services import insight_view


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
    if insight.engine != PUBLISHABLE_ENGINE:
        # The same rule as a post's: a simulation or a shared prepared example is no one's insight.
        _refuse("only an insight made by the real analysis can be public")
    if (insight.why or {}).get("personalised_because"):
        # Its words may be shaped by the profile, which is never public.
        _refuse("it was shaped by the profile")
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
    quran_ref = (
        (insight.quran_surah, insight.quran_ayah)
        if insight.quran_surah is not None and insight.quran_ayah is not None
        else None
    )
    hadith_ref = (
        (insight.hadith_collection, insight.hadith_number)
        if insight.hadith_collection is not None and insight.hadith_number is not None
        else None
    )
    corpus = await accept.cited_texts(db, quran_ref, hadith_ref)
    if await accept.leaks(db, list(texts.values()), corpus):
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
    if verse is None and hadith is None:
        # What made it public may have gone since (a ruling changed): nothing to show, no page.
        raise not_found(INSIGHT)
    texts = messages_for()
    return PublicInsightOut(
        id=insight.id,
        engine=insight.engine,
        label=insight_view.label_of(insight),
        title=insight.title,
        glimpse=insight.glimpse,
        relation=RelationType(insight.relation),
        relation_label=texts.relation_labels[insight.relation],
        **insight_view.shown_fields(insight, verse, hadith, awaiting, public=True),
        author=PublicAuthorOut(handle=owner.handle, public_name=owner.public_name)
        if owner.handle is not None and owner.public_name is not None
        else None,
        published_at=insight.published_at,
        disclosure=texts.ai_disclosure,
    )
