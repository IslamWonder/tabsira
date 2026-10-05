"""
Making the immutable copy of an insight that a post publishes.

The insight is read through an `InsightSource` and copied once. Every rule that decides what
may become public is applied here, whatever the source says: the insight must be verified and
owned by the caller, its evidence must resolve in the scripture store (a hadith only while it
is eligible, decisions 18 and 58), none of its platform text may look like scripture, and the photo
is kept only when its owner chose to show it and the scene is not sensitive. Scripture
itself is never copied: only references are.
"""

from __future__ import annotations

import uuid
from typing import NoReturn

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings
from src.errors import AppError, ErrorCode
from src.models.profile import AgeRange, Profile
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
from src.storage.photos import PhotoFacts

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
        _refuse("a hadith it cites is missing or not eligible (decisions 18 and 58)")


async def _photo_ref(
    db: AsyncSession,
    snapshot: InsightSnapshot,
    author: User,
    settings: Settings,
    *,
    publish_photo: bool,
) -> str | None:
    """
    Keep the photo's reference only if the photo rules of section 19 still allow publishing it.

    The owner chose to show the photo with this post (`publish_photo`), a photo was kept with
    their consent and the scene is not sensitive; and, as `PhotoFacts` checks again at publish
    time because facts change, the feature is on, the account has not since said it is under
    13 and it still agrees to keep photos. The reference is the private key of the owner's own
    copy: it is stored for the owner and for the photo store, and no public response carries it.
    """
    reference = snapshot.photo_ref
    if not publish_photo or not snapshot.photo_consent or not reference:
        return None
    if len(reference) > PHOTO_REF_MAX:
        return None
    profile = await db.scalar(select(Profile).where(Profile.user_id == author.id))
    facts = PhotoFacts(
        owner_id=author.id,
        age_range=profile.age_range if profile else AgeRange.UNKNOWN,
        sensitive_scene=snapshot.scene_sensitive,
        photo_storage_consent=bool(profile and profile.photo_storage_consent),
    )
    return None if facts.refusal(settings) else reference


async def refuse_under_13(
    db: AsyncSession,
    owner_id: uuid.UUID,
    message: str = "This insight cannot be published: the account declared it is under 13.",
) -> None:
    """Refuse everything for an account that said it is under 13 (v2 §5): a declared fact."""
    profile = await db.get(Profile, owner_id)
    if profile is not None and profile.age_range is AgeRange.UNDER_13:
        raise AppError(ErrorCode.UNDER_13_CANNOT_PUBLISH, message, status_code=409)


async def _refuse_under_13(db: AsyncSession, snapshot: InsightSnapshot) -> None:
    await refuse_under_13(db, snapshot.owner_id)


async def check_publishable(db: AsyncSession, snapshot: InsightSnapshot) -> None:
    """
    Refuse, with the reason, an insight that may not be shown to strangers.

    The one rule for a post and for an entry of the atlas: the owner did not say they are under
    13 (409 `UNDER_13_CANNOT_PUBLISH`), the insight is verified, every text fits and none reads
    like scripture, and its evidence resolves in the store, a hadith only while it is eligible
    (decisions 18 and 58).
    """
    await _refuse_under_13(db, snapshot)
    if not snapshot.verified:
        _refuse("it is not verified")
    _check_texts(snapshot)
    await _check_evidence(db, snapshot)


async def create_publication(
    db: AsyncSession,
    source: InsightSource,
    author: User,
    insight_id: int,
    settings: Settings,
    *,
    publish_photo: bool = False,
) -> InsightPublication:
    """
    Copy the author's verified insight into a publication, or refuse with a reason.

    `publish_photo` is the owner's choice to show the kept photo with the post; the copy for
    the public is made by `photo_service` once the post is published, never here.
    """
    snapshot = await source.load_for_publishing(db, insight_id, author.id)
    if snapshot is None or snapshot.owner_id != author.id or snapshot.insight_id != insight_id:
        raise AppError(ErrorCode.NOT_FOUND, "No such insight.", status_code=404)
    await check_publishable(db, snapshot)
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
        photo_ref=await _photo_ref(db, snapshot, author, settings, publish_photo=publish_photo),
    )
    db.add(publication)
    await db.flush()
    return publication
