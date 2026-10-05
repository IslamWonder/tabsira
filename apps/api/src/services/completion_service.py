"""
«تمّ» (v2 §15): one safe save that a double click or a retry cannot repeat.

The first «تمّ» on an insight, and only the first, marks it completed (a
completion, never mastery), counts the completion of its unit, records what
was shown (the verse and the hadith by reference, the concept, the time), lifts
the fog from its place in the world (made once, then reused) and, in the same
transaction, gives its concept a reveal of the world picture when the concept
is new (decision 59), records the threads it makes, and hides its treasure when
a verified one exists. A second «تمّ» changes nothing and answers the same
place and reveal. With memory switched off the
learner state and the exposures are not written; the insight and its place are.
For a signed-in owner who consented to keep photos, the first «تمّ» also keeps
the scan's photo privately (v2 §19); a guest's photo is never kept.
"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock
from src.config import Settings
from src.features import FeatureFlag
from src.messages import messages_for
from src.models import Insight, Treasure, WorldPlace, WorldReveal
from src.owner import Owner
from src.pipeline.engine import HadithRef, QuranRef
from src.schemas.insight import AfterOption, CompletionOut, CompletionRevealOut, PlaceOut
from src.services import learner_service, photo_service, progress_service, world_service
from src.services.content import load_regions
from src.services.insight_view import shown_evidence
from src.services.practice import UTC_ZONE, badges
from src.storage.photos import PhotoStore


def options() -> list[AfterOption]:
    """Return what the learner may do after «تمّ», in the order shown."""
    texts = messages_for()
    return [
        AfterOption(id="open_world", label=texts.option_open_world),
        AfterOption(id="new_scan", label=texts.option_new_scan),
        AfterOption(id="share", label=texts.option_share),
    ]


async def complete(
    db: AsyncSession,
    settings: Settings,
    owner: Owner,
    insight: Insight,
    *,
    redis: Redis,
    photos: PhotoStore,
) -> CompletionOut:
    """
    Complete an insight once and return what the learner may do next.

    The first «تمّ» also keeps the scan's photo, read from the buffer in `redis`, as the
    owner's private copy in `photos` when the rules of v2 §19 allow it (`photo_service`);
    for anyone the rules refuse, no photo is kept.
    """
    now = clock.utcnow()
    earned_before = await _earned(db, owner)
    first = (
        await db.execute(
            update(Insight)
            .where(Insight.id == insight.id, Insight.completed_at.is_(None))
            .values(completed_at=now)
            .returning(Insight.id)
        )
    ).one_or_none() is not None
    await db.refresh(insight)
    place_created = False
    reveal: WorldReveal | None = None
    reveal_created = False
    treasure_prepared = False
    if first:
        await remember(db, owner, insight)
        await photo_service.keep_from_buffer(db, redis, photos, insight)
        if settings.is_enabled(FeatureFlag.WORLD):
            written = await place_in_world(
                db, owner, insight, treasure=settings.is_enabled(FeatureFlag.TREASURE)
            )
            place_created, reveal, reveal_created, treasure_prepared = (
                written.place_created,
                written.reveal,
                written.reveal_created,
                written.treasure_prepared,
            )
        await db.commit()
    else:
        treasure_prepared = (
            await db.scalar(select(Treasure.id).where(Treasure.insight_id == insight.id))
        ) is not None
        reveal = await db.scalar(
            select(WorldReveal).where(
                owner.where(WorldReveal),
                WorldReveal.concept_key == world_service.concept_key(insight),
            )
        )
    return CompletionOut(
        insight_id=insight.id,
        completed_at=insight.completed_at or now,
        first_time=first,
        place=await _place(db, insight, created=place_created),
        reveal=CompletionRevealOut(id=reveal.id, landmark=reveal.slot == 0, created=reveal_created)
        if reveal is not None
        else None,
        treasure_prepared=treasure_prepared,
        badges_earned=sorted(await _earned(db, owner) - earned_before) if first else [],
        options=options(),
        suggest_account=messages_for().suggest_account
        if first and owner.is_guest and await _completed_count(db, owner) == 1
        else None,
        disclosure=messages_for().ai_disclosure,
    )


@dataclass(frozen=True)
class WorldWritten:
    """What the first completion of an insight wrote into the owner's world."""

    place_created: bool
    reveal: WorldReveal | None
    reveal_created: bool
    treasure_prepared: bool


async def place_in_world(
    db: AsyncSession, owner: Owner, insight: Insight, *, treasure: bool
) -> WorldWritten:
    """
    Put the completed insight in its place of the world and give its concept its reveal.

    Also records the threads it makes and, when `treasure` is on and a verified one exists, hides
    its treasure. Every time it writes is the insight's own `completed_at`, so the importer of the
    mock members (decision 66) calls the same function the first «تمّ» does.
    """
    region = await world_service.region_of(db, insight)
    place, place_created = await world_service.ensure_place(db, owner, region)
    insight.place_id = place.id
    await db.flush()
    reveal, reveal_created = await world_service.reveal_concept(db, owner, insight, place)
    await world_service.record_relations(db, owner, insight, place.id)
    prepared = treasure and await world_service.prepare_treasure(db, owner, insight, place)
    return WorldWritten(place_created, reveal, reveal_created, prepared)


async def remember(db: AsyncSession, owner: Owner, insight: Insight) -> None:
    """Count the completion of the insight's unit and record what was shown, unless memory is off."""
    if not await learner_service.memory_enabled(db, owner):
        return
    completed_at = insight.completed_at or clock.utcnow()
    await learner_service.record_completion(
        db,
        owner,
        unit_id=insight.learning_unit_id,
        path_version=insight.learning_path_version,
        at=completed_at,
    )
    verse, hadith = await shown_evidence(db, insight)
    db.add(
        learner_service.exposure(
            owner,
            kind=learner_service.KIND_COMPLETED,
            at=completed_at,
            insight_id=insight.id,
            quran=QuranRef(surah=verse.surah, ayah=verse.ayah) if verse else None,
            hadith=HadithRef(collection=hadith.collection.slug, number=hadith.number)
            if hadith
            else None,
            concept=str(insight.why.get("concept") or "") or None,
            unit_id=insight.learning_unit_id,
        )
    )


async def _place(db: AsyncSession, insight: Insight, *, created: bool) -> PlaceOut | None:
    if insight.place_id is None:
        return None
    place = (await db.scalars(select(WorldPlace).where(WorldPlace.id == insight.place_id))).one()
    return PlaceOut(
        id=place.id,
        region_id=place.region_id,
        name=load_regions().name_of(place.region_id),
        created=created,
    )


async def _completed_count(db: AsyncSession, owner: Owner) -> int:
    count = await db.scalar(
        select(func.count())
        .select_from(Insight)
        .where(owner.where(Insight), Insight.completed_at.is_not(None))
    )
    return int(count or 0)


async def _earned(db: AsyncSession, owner: Owner) -> set[str]:
    """Return the badges the owner holds now (days counted in UTC)."""
    log = await progress_service.practice_log(db, owner)
    return {badge_id for badge_id, moment in badges(log, UTC_ZONE).items() if moment is not None}
