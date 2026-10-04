"""
The learner's world (v2 §16): places, recorded threads and the treasures that wait in them.

A completed insight lifts the fog from the region of its unit's domain: the
place is created once per owner and region, then reused. Threads are recorded,
never inferred: two places are joined only when two completed insights came
from the same scene, or when the learning path names the unit of one as a
prerequisite of the unit of the other. The fog means "not discovered yet", not
a lack in the learner; nothing here is a score.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import cast

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock, messages
from src.config import Settings
from src.errors import AppError, ErrorCode
from src.models import (
    Insight,
    InsightOrigin,
    LearningDomain,
    LearningUnit,
    RelationReason,
    Treasure,
    WorldPlace,
    WorldRelation,
)
from src.owner import PLACE, TREASURE, Owner, not_found
from src.pipeline.engine import HadithRef, QuranRef
from src.schemas.insight import InsightHadith, InsightQuran
from src.schemas.world import (
    PlaceInsightOut,
    PlaceOut,
    PositionOut,
    RegionOut,
    RelationOut,
    TreasureFlag,
    TreasureOut,
    TreasureUnitOut,
    WorldOut,
)
from src.services import learner_service, treasure
from src.services.content import Region, load_regions
from src.services.insight_view import evidence


async def region_of(db: AsyncSession, insight: Insight) -> Region:
    """Return the region of the insight's unit's domain, or the fallback region."""
    domain_id = None
    if insight.learning_unit_id and insight.learning_path_version:
        domain_id = await db.scalar(
            select(LearningUnit.domain_id).where(
                LearningUnit.path_version == insight.learning_path_version,
                LearningUnit.id == insight.learning_unit_id,
            )
        )
    return load_regions().for_domain(domain_id)


async def ensure_place(db: AsyncSession, owner: Owner, region: Region) -> tuple[WorldPlace, bool]:
    """Return the owner's place of a region, creating it once; say whether it was created."""
    column = WorldPlace.user_id if owner.user_id is not None else WorldPlace.guest_key
    created = await db.scalar(
        insert(WorldPlace)
        .values(**owner.columns(), region_id=region.id, regions_version=load_regions().version)
        .on_conflict_do_nothing(
            index_elements=[column, WorldPlace.region_id], index_where=column.is_not(None)
        )
        .returning(WorldPlace.id)
    )
    # The insert above, or a concurrent one, made it: exactly one row exists.
    place = (
        await db.scalars(
            select(WorldPlace).where(owner.where(WorldPlace), WorldPlace.region_id == region.id)
        )
    ).one()
    return place, created is not None


async def record_relations(
    db: AsyncSession, owner: Owner, insight: Insight, place_id: uuid.UUID
) -> None:
    """Record the threads this completion, in place `place_id`, makes: same scene, prerequisites."""
    others = (
        await db.scalars(
            select(Insight).where(
                owner.where(Insight),
                Insight.id != insight.id,
                Insight.completed_at.is_not(None),
                Insight.place_id.is_not(None),
                Insight.place_id != place_id,
            )
        )
    ).all()
    prerequisites = await _prerequisites(db, insight)
    for other in others:
        reasons = []
        if _same_scene(insight, other):
            reasons.append(RelationReason.SAME_SCENE)
        if other.learning_unit_id and (
            other.learning_unit_id in prerequisites
            or insight.learning_unit_id in await _prerequisites(db, other)
        ):
            reasons.append(RelationReason.PREREQUISITE)
        for reason in reasons:
            # The query kept only insights that have a place.
            other_place = cast("uuid.UUID", other.place_id)
            await _relate(db, (place_id, insight.id), (other_place, other.id), reason)


def _same_scene(one: Insight, other: Insight) -> bool:
    if one.origin is InsightOrigin.SCAN:
        return other.scan_id == one.scan_id
    return other.origin is InsightOrigin.TUTORIAL and other.tutorial_scene == one.tutorial_scene


async def _prerequisites(db: AsyncSession, insight: Insight) -> set[str]:
    if not insight.learning_unit_id or not insight.learning_path_version:
        return set()
    found = await db.scalar(
        select(LearningUnit.prerequisites).where(
            LearningUnit.path_version == insight.learning_path_version,
            LearningUnit.id == insight.learning_unit_id,
        )
    )
    return set(found or [])


async def _relate(
    db: AsyncSession,
    one: tuple[uuid.UUID, uuid.UUID],
    other: tuple[uuid.UUID, uuid.UUID],
    reason: RelationReason,
) -> None:
    """Record a thread between two (place, insight) pairs, the lower place first."""
    (low_place, low_insight), (high_place, high_insight) = sorted([one, other])
    await db.execute(
        insert(WorldRelation)
        .values(
            place_a_id=low_place,
            place_b_id=high_place,
            reason=reason,
            insight_a_id=low_insight,
            insight_b_id=high_insight,
        )
        .on_conflict_do_nothing(constraint="uq_world_relations_places_reason")
    )


async def prepare_treasure(
    db: AsyncSession, owner: Owner, insight: Insight, place: WorldPlace
) -> bool:
    """Hide the insight's treasure in its place when a verified candidate exists; say if one did."""
    if not insight.learning_unit_id or not insight.learning_path_version:
        return False
    excluded: list[QuranRef | HadithRef] = []
    if insight.quran_surah is not None and insight.quran_ayah is not None:
        excluded.append(QuranRef(surah=insight.quran_surah, ayah=insight.quran_ayah))
    if insight.hadith_collection is not None and insight.hadith_number is not None:
        excluded.append(
            HadithRef(collection=insight.hadith_collection, number=insight.hadith_number)
        )
    context = await learner_service.learner_context(db, owner)
    excluded += [*context.seen_quran, *context.seen_hadith]
    chosen = await treasure.choose(
        db,
        unit_id=insight.learning_unit_id,
        path_version=insight.learning_path_version,
        excluded=excluded,
    )
    if chosen is None:
        return False
    ref = chosen.ref
    db.add(
        Treasure(
            insight_id=insight.id,
            place_id=place.id,
            kind=chosen.kind,
            quran_surah=ref.surah if isinstance(ref, QuranRef) else None,
            quran_ayah=ref.ayah if isinstance(ref, QuranRef) else None,
            hadith_collection=ref.collection if isinstance(ref, HadithRef) else None,
            hadith_number=ref.number if isinstance(ref, HadithRef) else None,
            learning_unit_id=chosen.unit_id,
            learning_path_version=insight.learning_path_version,
            created_at=clock.utcnow(),
        )
    )
    await db.flush()
    return True


def _windows(settings: Settings) -> dict[str, timedelta]:
    return {
        "reveal_after": timedelta(days=settings.treasure_reveal_after_days),
        "return_after": timedelta(hours=settings.treasure_return_after_hours),
    }


async def ready_treasures(
    db: AsyncSession, settings: Settings, owner: Owner, places: list[WorldPlace]
) -> dict[uuid.UUID, Treasure]:
    """Return, per place, a hidden treasure the learner may reveal now."""
    if not settings.feature_treasure or not places:
        return {}
    by_id = {place.id: place for place in places}
    hidden = (
        await db.scalars(
            select(Treasure)
            .where(Treasure.place_id.in_(by_id), Treasure.revealed_at.is_(None))
            .order_by(Treasure.created_at)
        )
    ).all()
    completed = (
        await db.scalars(
            select(Insight).where(owner.where(Insight), Insight.completed_at.is_not(None))
        )
    ).all()
    insights = {insight.id: insight for insight in completed}
    now = clock.utcnow()
    ready: dict[uuid.UUID, Treasure] = {}
    for item in hidden:
        source = insights.get(item.insight_id)
        concept = source.why.get("concept") if source is not None else None
        related = any(
            other.id != item.insight_id
            and other.completed_at is not None
            and other.completed_at > item.created_at
            and _related(other, item, concept)
            for other in completed
        )
        if item.place_id not in ready and treasure.treasure_ready(
            item.created_at,
            now,
            last_visit=by_id[item.place_id].last_visited_at,
            related_completed_after=related,
            **_windows(settings),
        ):
            ready[item.place_id] = item
    return ready


def _related(other: Insight, item: Treasure, concept: str | None) -> bool:
    """Tell whether a later insight is close to a treasure: same place, same unit or same concept."""
    return (
        other.place_id == item.place_id
        or other.learning_unit_id == item.learning_unit_id
        or (bool(concept) and other.why.get("concept") == concept)
    )


async def _places(db: AsyncSession, owner: Owner) -> list[WorldPlace]:
    return list(
        (
            await db.scalars(
                select(WorldPlace).where(owner.where(WorldPlace)).order_by(WorldPlace.created_at)
            )
        ).all()
    )


async def place_out(
    db: AsyncSession, place: WorldPlace, treasures: dict[uuid.UUID, Treasure]
) -> PlaceOut:
    insights = (
        await db.scalars(
            select(Insight)
            .where(Insight.place_id == place.id, Insight.completed_at.is_not(None))
            .order_by(Insight.completed_at)
        )
    ).all()
    ready = treasures.get(place.id)
    return PlaceOut(
        id=place.id,
        region_id=place.region_id,
        name=load_regions().name_of(place.region_id),
        created_at=place.created_at,
        last_visited_at=place.last_visited_at,
        insights=[
            PlaceInsightOut(id=row.id, title=row.title, completed_at=row.completed_at)
            for row in insights
            if row.completed_at is not None
        ],
        treasure=TreasureFlag(id=ready.id) if ready else None,
    )


async def world(db: AsyncSession, settings: Settings, owner: Owner | None) -> WorldOut:
    """Return the whole map: every region with its fog, the owner's places and threads."""
    regions = load_regions()
    places = await _places(db, owner) if owner is not None else []
    by_region = {place.region_id: place for place in places}
    rows = await db.execute(
        select(LearningDomain.id, LearningDomain.title).where(
            LearningDomain.path_version == regions.path_version
        )
    )
    titles = {row.id: row.title for row in rows}
    treasures = await ready_treasures(db, settings, owner, places) if owner is not None else {}
    place_ids = [place.id for place in places]
    relations = (
        (
            await db.scalars(
                select(WorldRelation)
                .where(
                    or_(
                        WorldRelation.place_a_id.in_(place_ids),
                        WorldRelation.place_b_id.in_(place_ids),
                    )
                )
                .order_by(WorldRelation.id)
            )
        ).all()
        if place_ids
        else []
    )
    return WorldOut(
        version=regions.version,
        path_version=regions.path_version,
        regions=[
            RegionOut(
                id=region.id,
                domain_id=region.domain_id,
                name=region.name,
                domain_title=titles.get(region.domain_id, ""),
                position=PositionOut(x=region.position.x, y=region.position.y),
                fog=region.id not in by_region,
                place_id=by_region[region.id].id if region.id in by_region else None,
            )
            for region in regions.regions
        ],
        places=[await place_out(db, place, treasures) for place in places],
        relations=[
            RelationOut(
                place_a_id=relation.place_a_id,
                place_b_id=relation.place_b_id,
                reason=relation.reason,
                reason_label=messages.WORLD_RELATION_REASONS[relation.reason.value],
                question=messages.RELATION_THREAD_QUESTION,
                insight_ids=[relation.insight_a_id, relation.insight_b_id],
            )
            for relation in relations
        ],
    )


async def visit(
    db: AsyncSession, settings: Settings, owner: Owner | None, place_id: uuid.UUID
) -> PlaceOut:
    """Record that the learner opened a place, and return it with a treasure that is now ready."""
    if owner is None:
        raise not_found(PLACE)
    place = await db.scalar(
        select(WorldPlace).where(WorldPlace.id == place_id, owner.where(WorldPlace))
    )
    if place is None:
        raise not_found(PLACE)
    place.last_visited_at = clock.utcnow()
    await db.flush()
    treasures = await ready_treasures(db, settings, owner, [place])
    out = await place_out(db, place, treasures)
    await db.commit()
    return out


async def reveal(
    db: AsyncSession, settings: Settings, owner: Owner | None, treasure_id: uuid.UUID
) -> TreasureOut:
    """Reveal a treasure that is ready (again, idempotently, once revealed) and record the exposure."""
    if owner is None:
        raise not_found(TREASURE)
    row = (
        await db.execute(
            select(Treasure, Insight)
            .join(Insight, Insight.id == Treasure.insight_id)
            .where(Treasure.id == treasure_id, owner.where(Insight))
        )
    ).one_or_none()
    if row is None:
        raise not_found(TREASURE)
    item, insight = row
    if item.revealed_at is None:
        place = await db.get(WorldPlace, item.place_id)
        ready = await ready_treasures(db, settings, owner, [place] if place else [])
        if item.place_id not in ready or ready[item.place_id].id != item.id:
            raise AppError(
                ErrorCode.TREASURE_NOT_READY, "The treasure shows on return.", status_code=409
            )
        item.revealed_at = clock.utcnow()
        quran = (
            QuranRef(surah=item.quran_surah, ayah=item.quran_ayah)
            if item.quran_surah is not None and item.quran_ayah is not None
            else None
        )
        hadith = (
            HadithRef(collection=item.hadith_collection, number=item.hadith_number)
            if item.hadith_collection is not None and item.hadith_number is not None
            else None
        )
        if await learner_service.memory_enabled(db, owner):
            db.add(
                learner_service.exposure(
                    owner,
                    kind="treasure",
                    at=item.revealed_at,
                    insight_id=insight.id,
                    quran=quran,
                    hadith=hadith,
                    concept=None,
                    unit_id=item.learning_unit_id,
                )
            )
        await db.commit()
    return await treasure_out(db, item)


async def treasure_out(db: AsyncSession, item: Treasure) -> TreasureOut:
    quran = (
        (item.quran_surah, item.quran_ayah)
        if item.quran_surah is not None and item.quran_ayah is not None
        else None
    )
    hadith_ref = (
        (item.hadith_collection, item.hadith_number)
        if item.hadith_collection is not None and item.hadith_number is not None
        else None
    )
    verse, hadith, _awaiting = await evidence(db, quran, hadith_ref)
    unit = await db.get(LearningUnit, (item.learning_path_version, item.learning_unit_id))
    return TreasureOut(
        id=item.id,
        kind=item.kind,
        kind_label=messages.TREASURE_KIND_LABELS[item.kind.value],
        insight_id=item.insight_id,
        place_id=item.place_id,
        quran=InsightQuran(tag=messages.QURAN_TAG, verse=verse, why=None) if verse else None,
        hadith=InsightHadith(tag=messages.SUNNAH_TAG, hadith=hadith, why=None) if hadith else None,
        learning_unit=TreasureUnitOut(id=unit.id, title=unit.title) if unit else None,
        revealed_at=item.revealed_at,
        disclosure=messages.AI_DISCLOSURE,
    )
