"""
The learner's world (v2 §16): places, recorded threads and the treasures that wait in them.

A completed insight lifts the fog from the region of its unit's domain: the
place is created once per owner and region, then reused. Threads are recorded,
never inferred: two places are joined only when two completed insights came
from the same scene, or when the learning path names the unit of one as a
prerequisite of the unit of the other. The fog means "not discovered yet", not
a lack in the learner; nothing here is a score.

A treasure is read from the store when it shows, like any evidence: one whose
text no longer shows (its hadith since ruled other than صحيح or حسن) is neither
flagged nor revealed, and records no exposure.

The world picture (decision 59) shows what was learned as circles lifted from
its clouds: one reveal per owner and concept, made by the completion that
learned the concept first, in the lowest slot its region's layout still has
free, and never moved. Learning a concept again widens nothing; a region whose
slots are all taken widens no more, and its insights gather under its landmark.
"""

from __future__ import annotations

from datetime import timedelta
from typing import cast

from sqlalchemy import Text, exists, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from src import clock
from src.config import Settings
from src.errors import AppError, ErrorCode
from src.features import FeatureFlag
from src.messages import messages_for
from src.models import (
    Insight,
    InsightOrigin,
    LearningDomain,
    LearningUnit,
    RelationReason,
    Treasure,
    WorldPlace,
    WorldRelation,
    WorldReveal,
)
from src.owner import PLACE, TREASURE, Owner, not_found
from src.pipeline.engine import HadithRef, QuranRef
from src.routers.scripture import HadithOut, QuranVerseOut
from src.schemas.insight import InsightHadith, InsightQuran
from src.schemas.world import (
    PlaceInsightOut,
    PositionOut,
    RegionOut,
    RelationOut,
    RevealOut,
    TreasureFlag,
    TreasureOut,
    TreasureUnitOut,
    WorldOut,
    WorldPlaceOut,
)
from src.services import learner_service, treasure
from src.services.content import Region, load_layout, load_regions
from src.services.evidence_view import load_evidence
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


def concept_key(insight: Insight) -> str:
    """
    Name the concept an insight teaches: its learning path unit, whose id the path keeps.

    masar.md gives its 96 units fixed ids that a machine-made title never replaces; an
    insight with no unit is its own concept, so two unknown ones are never merged.
    """
    if insight.learning_unit_id:
        return f"unit:{insight.learning_unit_id}"
    return f"insight:{insight.id}"


# `concept_key` written in SQL, for the repair's query.
_CONCEPT_OF_INSIGHT = func.coalesce(
    literal("unit:") + func.nullif(Insight.learning_unit_id, ""),
    literal("insight:") + Insight.id.cast(Text),
)


async def _reveal_of(db: AsyncSession, owner: Owner, key: str) -> WorldReveal | None:
    found: WorldReveal | None = await db.scalar(
        select(WorldReveal).where(owner.where(WorldReveal), WorldReveal.concept_key == key)
    )
    return found


async def _taken_slots(
    db: AsyncSession, owner: Owner, layout_version: str, region_id: str
) -> set[int]:
    return set(
        await db.scalars(
            select(WorldReveal.slot).where(
                owner.where(WorldReveal),
                WorldReveal.layout_version == layout_version,
                WorldReveal.region_id == region_id,
            )
        )
    )


async def reveal_concept(
    db: AsyncSession, owner: Owner, insight: Insight, place: WorldPlace
) -> tuple[WorldReveal | None, bool]:
    """
    Give a learned insight's concept its circle of the picture, once; say whether it was made now.

    The concept's reveal, when the owner already has one, comes back unchanged. Otherwise
    the concept takes the lowest slot of its region the layout still has free, with the
    circle the layout gives that slot, and None comes back when no slot is free. Two
    completions at once take neither one concept nor one slot twice: both are unique, and
    the one that loses the race reads again and takes the next slot or the winner's reveal.
    """
    key = concept_key(insight)
    layout = load_layout()
    region = layout.region(place.region_id)
    # Each lost race means another reveal was made: one per slot at most, then the concept's.
    attempts = len(region.slots) + 1 if region is not None else 1
    for _attempt in range(attempts):
        existing = await _reveal_of(db, owner, key)
        if existing is not None:
            return existing, False
        if region is None:
            return None, False
        taken = await _taken_slots(db, owner, layout.version, region.id)
        free = next((index for index in range(len(region.slots)) if index not in taken), None)
        if free is None:
            return None, False
        slot = region.slots[free]
        made = await db.scalar(
            insert(WorldReveal)
            .values(
                **owner.columns(),
                insight_id=insight.id,
                place_id=place.id,
                concept_key=key,
                region_id=region.id,
                layout_version=layout.version,
                slot=free,
                theme=region.theme,
                x=slot.x,
                y=slot.y,
                radius=slot.radius,
                learned_at=insight.completed_at or clock.utcnow(),
            )
            .on_conflict_do_nothing()
            .returning(WorldReveal.id)
        )
        if made is not None:
            return await db.get_one(WorldReveal, made), True
    return None, False


async def _place_of(db: AsyncSession, owner: Owner, insight: Insight) -> WorldPlace:
    """Return the insight's place, making it (and pointing the insight at it) when it has none."""
    if insight.place_id is not None:
        return await db.get_one(WorldPlace, insight.place_id)
    place, _created = await ensure_place(db, owner, await region_of(db, insight))
    insight.place_id = place.id
    await db.flush()
    return place


async def ensure_reveals(db: AsyncSession, owner: Owner) -> bool:
    """
    Reveal every learned concept of the owner that has no reveal yet, in the order learned.

    A completion makes its reveal in its own transaction; this gives one to what was
    learned before reveals existed or while the world was switched off, from the
    completed insights alone, and is safe to run again or at the same time. What it
    makes counts as shown: an old learning does not play the effect of a new one. A
    concept whose region has no free slot left is passed over without a query, so a
    full region costs nothing on later loads. Return whether it made anything.
    """
    pending = (
        await db.scalars(
            select(Insight)
            .where(
                owner.where(Insight),
                Insight.completed_at.is_not(None),
                ~exists().where(
                    owner.where(WorldReveal), WorldReveal.concept_key == _CONCEPT_OF_INSIGHT
                ),
            )
            .order_by(Insight.completed_at, Insight.id)
        )
    ).all()
    if not pending:
        return False
    layout = load_layout()
    places = {place.id: place for place in await _places(db, owner)}
    taken: dict[str, int] = {}
    for given in await _reveals(db, owner):
        if given.layout_version == layout.version:
            taken[given.region_id] = taken.get(given.region_id, 0) + 1
    made = False
    done: set[str] = set()
    for insight in pending:
        key = concept_key(insight)
        if key in done:
            # A later insight of a concept this loop already revealed, or found no room for.
            continue
        done.add(key)
        known = places.get(insight.place_id) if insight.place_id is not None else None
        if known is not None and not _has_room(known.region_id, taken):
            continue
        place = known or await _place_of(db, owner, insight)
        reveal, created = await reveal_concept(db, owner, insight, place)
        if reveal is not None and created:
            reveal.shown_at = clock.utcnow()
            taken[place.region_id] = taken.get(place.region_id, 0) + 1
            made = True
    await db.flush()
    return made


def _has_room(region_id: str, taken: dict[str, int]) -> bool:
    """Tell whether the current layout still has a free slot in a region, from the slots taken."""
    region = load_layout().region(region_id)
    return region is not None and taken.get(region_id, 0) < len(region.slots)


async def mark_shown(db: AsyncSession, owner: Owner | None, reveal_ids: list[int]) -> None:
    """Record that the world played these reveals of the owner's; another owner's ids change nothing."""
    if owner is None:
        return
    await db.execute(
        update(WorldReveal)
        .where(
            owner.where(WorldReveal),
            WorldReveal.id.in_(reveal_ids),
            WorldReveal.shown_at.is_(None),
        )
        .values(shown_at=clock.utcnow())
    )
    await db.commit()


def reveal_out(reveal: WorldReveal) -> RevealOut:
    region = load_layout().region(reveal.region_id)
    return RevealOut(
        id=reveal.id,
        place_id=reveal.place_id,
        region_id=reveal.region_id,
        insight_id=reveal.insight_id,
        landmark=reveal.slot == 0,
        theme=reveal.theme,
        icon=region.icon if region is not None else "",
        x=reveal.x,
        y=reveal.y,
        radius=reveal.radius,
        learned_at=reveal.learned_at,
        shown=reveal.shown_at is not None,
    )


async def _reveals(db: AsyncSession, owner: Owner) -> list[WorldReveal]:
    return list(
        (
            await db.scalars(
                select(WorldReveal)
                .where(owner.where(WorldReveal))
                .order_by(WorldReveal.learned_at, WorldReveal.id)
            )
        ).all()
    )


async def record_relations(db: AsyncSession, owner: Owner, insight: Insight, place_id: int) -> None:
    """Record the threads this completion, in place `place_id`, makes: same scene, prerequisites."""
    others = (
        await db.scalars(
            select(Insight)
            # Only the fields the relation checks read (see ready_treasures).
            .options(
                load_only(
                    Insight.id,
                    Insight.scan_id,
                    Insight.origin,
                    Insight.tutorial_scene,
                    Insight.place_id,
                    Insight.learning_unit_id,
                    Insight.learning_path_version,
                )
            )
            .where(
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
            other_place = cast("int", other.place_id)
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
    one: tuple[int, int],
    other: tuple[int, int],
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
) -> dict[int, Treasure]:
    """Return, per place, a hidden treasure the learner may reveal now."""
    if not settings.is_enabled(FeatureFlag.TREASURE) or not places:
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
            select(Insight)
            # Only the fields the readiness and relation checks read; a
            # completion carries large text columns this loop never opens.
            .options(
                load_only(
                    Insight.id,
                    Insight.completed_at,
                    Insight.why,
                    Insight.scan_id,
                    Insight.origin,
                    Insight.tutorial_scene,
                    Insight.place_id,
                    Insight.learning_unit_id,
                )
            )
            .where(owner.where(Insight), Insight.completed_at.is_not(None))
        )
    ).all()
    insights = {insight.id: insight for insight in completed}
    now = clock.utcnow()
    # What each treasure's references resolve to now, read from the store in
    # bulk: one query per text kind, not per treasure.
    refs = {item.id: _refs(item) for item in hidden}
    shown = await load_evidence(
        db,
        {quran for quran, _ in refs.values() if quran is not None},
        {hadith for _, hadith in refs.values() if hadith is not None},
    )
    ready: dict[int, Treasure] = {}
    for item in hidden:
        quran, hadith_ref = refs[item.id]
        verse = shown.quran.get(quran) if quran is not None else None
        hadith = shown.hadith.get(hadith_ref) if hadith_ref is not None else None
        if verse is None and hadith is None:
            continue
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
    db: AsyncSession,
    place: WorldPlace,
    treasures: dict[int, Treasure],
    reveals: dict[str, int] | None = None,
) -> WorldPlaceOut:
    """
    Return a place with its completed insights; `reveals` maps concept keys to reveal ids.

    Without `reveals` the owner's reveals are read here, for a place returned alone.
    """
    insights = (
        await db.scalars(
            select(Insight)
            .where(Insight.place_id == place.id, Insight.completed_at.is_not(None))
            .order_by(Insight.completed_at)
        )
    ).all()
    if reveals is None:
        owner = Owner(user_id=place.user_id, guest_key=place.guest_key)
        reveals = {row.concept_key: row.id for row in await _reveals(db, owner)}
    ready = treasures.get(place.id)
    return WorldPlaceOut(
        id=place.id,
        region_id=place.region_id,
        name=load_regions().name_of(place.region_id),
        created_at=place.created_at,
        last_visited_at=place.last_visited_at,
        insights=[
            PlaceInsightOut(
                id=row.id,
                title=row.title,
                completed_at=row.completed_at,
                reveal_id=reveals.get(concept_key(row)),
            )
            for row in insights
            if row.completed_at is not None
        ],
        treasure=TreasureFlag(id=ready.id) if ready else None,
    )


async def world(db: AsyncSession, settings: Settings, owner: Owner | None) -> WorldOut:
    """
    Return the whole map: every region with its fog, the owner's places, reveals and threads.

    What was learned without a reveal (before reveals existed, or with the world off)
    gets one first, so the picture always says what the completed insights say.
    """
    regions = load_regions()
    if owner is not None and await ensure_reveals(db, owner):
        await db.commit()
    reveals = await _reveals(db, owner) if owner is not None else []
    by_concept = {reveal.concept_key: reveal.id for reveal in reveals}
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
        layout_version=load_layout().version,
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
        places=[await place_out(db, place, treasures, by_concept) for place in places],
        relations=[
            RelationOut(
                place_a_id=relation.place_a_id,
                place_b_id=relation.place_b_id,
                reason=relation.reason,
                reason_label=messages_for().world_relation_reasons[relation.reason.value],
                question=messages_for().relation_thread_question,
                insight_ids=[relation.insight_a_id, relation.insight_b_id],
            )
            for relation in relations
        ],
        reveals=[reveal_out(reveal) for reveal in reveals],
    )


async def visit(
    db: AsyncSession, settings: Settings, owner: Owner | None, place_id: int
) -> WorldPlaceOut:
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
    db: AsyncSession, settings: Settings, owner: Owner | None, treasure_id: int
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
    verse, hadith = await _shown(db, item)
    if verse is None and hadith is None:
        # Its text no longer shows: there is nothing to reveal, now or again.
        raise not_found(TREASURE)
    if item.revealed_at is None:
        place = await db.get(WorldPlace, item.place_id)
        ready = await ready_treasures(db, settings, owner, [place] if place else [])
        if item.place_id not in ready or ready[item.place_id].id != item.id:
            raise AppError(
                ErrorCode.TREASURE_NOT_READY, "The treasure shows on return.", status_code=409
            )
        item.revealed_at = clock.utcnow()
        if await learner_service.memory_enabled(db, owner):
            db.add(
                learner_service.exposure(
                    owner,
                    kind=learner_service.KIND_TREASURE,
                    at=item.revealed_at,
                    insight_id=insight.id,
                    quran=QuranRef(surah=verse.surah, ayah=verse.ayah) if verse else None,
                    hadith=(
                        HadithRef(collection=hadith.collection.slug, number=hadith.number)
                        if hadith
                        else None
                    ),
                    concept=None,
                    unit_id=item.learning_unit_id,
                )
            )
        await db.commit()
    return await treasure_out(db, item, verse, hadith)


def _refs(item: Treasure) -> tuple[tuple[int, int] | None, tuple[str, str] | None]:
    """Return the scripture references a treasure keeps, as `evidence` takes them."""
    quran = (
        (item.quran_surah, item.quran_ayah)
        if item.quran_surah is not None and item.quran_ayah is not None
        else None
    )
    hadith = (
        (item.hadith_collection, item.hadith_number)
        if item.hadith_collection is not None and item.hadith_number is not None
        else None
    )
    return quran, hadith


async def _shown(db: AsyncSession, item: Treasure) -> tuple[QuranVerseOut | None, HadithOut | None]:
    """Return the treasure's verse or hadith as it shows now (decision 65)."""
    quran, hadith_ref = _refs(item)
    verse, hadith = await evidence(db, quran, hadith_ref)
    return verse, hadith


async def treasure_out(
    db: AsyncSession, item: Treasure, verse: QuranVerseOut | None, hadith: HadithOut | None
) -> TreasureOut:
    unit = await db.get(LearningUnit, (item.learning_path_version, item.learning_unit_id))
    return TreasureOut(
        id=item.id,
        kind=item.kind,
        kind_label=messages_for().treasure_kind_labels[item.kind.value],
        insight_id=item.insight_id,
        place_id=item.place_id,
        quran=InsightQuran(tag=messages_for().quran_tag, verse=verse, why=None) if verse else None,
        hadith=InsightHadith(tag=messages_for().sunnah_tag, hadith=hadith, why=None)
        if hadith
        else None,
        learning_unit=TreasureUnitOut(id=unit.id, title=unit.title) if unit else None,
        revealed_at=item.revealed_at,
        disclosure=messages_for().ai_disclosure,
    )
