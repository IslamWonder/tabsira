"""
Making the immutable copy of an insight that a post publishes.

The insight is read through an `InsightSource` and copied once. Every rule that decides what
may become public is applied here, whatever the source says: the insight must be verified and
owned by the caller, its evidence must resolve in the scripture store (a hadith only while its
ruling makes it eligible), none of its platform text may look like scripture, and the photo
is kept only when its owner agreed to publish it and the scene is not sensitive. Scripture
itself is never copied: only references are.
"""

from __future__ import annotations

from typing import NoReturn

from sqlalchemy.ext.asyncio import AsyncSession

from src.errors import AppError, ErrorCode
from src.models.social import (
    EXPLANATION_MAX,
    GLIMPSE_MAX,
    STEP_MAX,
    TITLE_MAX,
    InsightPublication,
)
from src.models.user import User
from src.pipeline.leak_guard import LeakGuard
from src.services import evidence_view
from src.services.insight_source import InsightSnapshot, InsightSource

MAX_REFS = 3
MAX_CONCEPTS = 5
CONCEPT_MAX = 60
RELATION_MAX = 32
PHOTO_REF_MAX = 512

_LEAK_GUARD = LeakGuard()


def _refuse(why: str) -> NoReturn:
    """Refuse the insight with the reason, which names what to fix."""
    message = f"This insight cannot be published: {why}."
    raise AppError(ErrorCode.INSIGHT_NOT_PUBLISHABLE, message, status_code=409)


def _check_texts(snapshot: InsightSnapshot) -> None:
    """Refuse a text that does not fit its column, or that reads like scripture."""
    limits = {
        "title": (snapshot.title, TITLE_MAX),
        "glimpse": (snapshot.glimpse, GLIMPSE_MAX),
        "explanation": (snapshot.explanation_excerpt, EXPLANATION_MAX),
        "step": (snapshot.step_text or "", STEP_MAX),
        "relation": (snapshot.relation_type, RELATION_MAX),
    }
    for name, (text, limit) in limits.items():
        if len(text) > limit:
            _refuse(f"its {name} is longer than {limit} characters")
    if not snapshot.title.strip() or not snapshot.glimpse.strip():
        _refuse("it has no title or no glimpse")
    texts = {name: text for name, (text, _) in limits.items() if name != "relation"}
    if any(_LEAK_GUARD.check(text).leaked for text in texts.values()):
        _refuse("its text looks like scripture, which only the store may supply")


async def _check_evidence(db: AsyncSession, snapshot: InsightSnapshot) -> None:
    """Refuse an insight whose evidence is missing, or no longer holds."""
    quran = [(ref.surah, ref.ayah) for ref in snapshot.quran_refs]
    hadith = [(ref.collection, ref.number) for ref in snapshot.hadith_refs]
    if not quran and not hadith:
        _refuse("it cites no evidence")
    if len(quran) > MAX_REFS or len(hadith) > MAX_REFS:
        _refuse(f"it cites more than {MAX_REFS} verses or hadiths")
    found = await evidence_view.load_evidence(db, quran, hadith)
    if not set(quran) <= set(found.quran):
        _refuse("a verse it cites is not in the store")
    if not set(hadith) <= set(found.hadith):
        _refuse("a hadith it cites is missing or has no sahih or hasan ruling")


def _photo_ref(snapshot: InsightSnapshot) -> str | None:
    """Keep the photo's reference only if its owner agreed to publish it and the scene is not sensitive."""
    if not snapshot.photo_consent or snapshot.scene_sensitive or not snapshot.photo_ref:
        return None
    return snapshot.photo_ref if len(snapshot.photo_ref) <= PHOTO_REF_MAX else None


async def create_publication(
    db: AsyncSession, source: InsightSource, author: User, insight_id: int
) -> InsightPublication:
    """Copy the author's verified insight into a publication, or refuse with a reason."""
    snapshot = await source.load_for_publishing(db, insight_id, author.id)
    if snapshot is None or snapshot.owner_id != author.id or snapshot.insight_id != insight_id:
        raise AppError(ErrorCode.NOT_FOUND, "No such insight.", status_code=404)
    if not snapshot.verified:
        _refuse("it is not verified")
    _check_texts(snapshot)
    await _check_evidence(db, snapshot)
    publication = InsightPublication(
        author_id=author.id,
        insight_id=snapshot.insight_id,
        insight_version=snapshot.version,
        title=snapshot.title.strip(),
        glimpse=snapshot.glimpse.strip(),
        relation_type=snapshot.relation_type,
        concepts=[c.strip()[:CONCEPT_MAX] for c in snapshot.concepts if c.strip()][:MAX_CONCEPTS],
        quran_refs=[{"surah": r.surah, "ayah": r.ayah} for r in snapshot.quran_refs],
        hadith_refs=[
            {"collection": r.collection, "number": r.number} for r in snapshot.hadith_refs
        ],
        explanation_excerpt=snapshot.explanation_excerpt.strip(),
        step_text=(snapshot.step_text or "").strip() or None,
        photo_ref=_photo_ref(snapshot),
    )
    db.add(publication)
    await db.flush()
    return publication
