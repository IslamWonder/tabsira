"""
What the engine may know of a learner, and what a completion records.

The profile reaches the engine only when its owner keeps personalization on,
and the history (the texts already shown, the units completed) only when
memory is on (v2 §5). A guest has no profile: the engine gets the neutral
defaults, `unknown` everywhere, and nothing is assumed. A completion counts in
`learner_unit_states` as a completion, never as mastery, and records what was
shown in `evidence_exposures`; with memory off, neither is written.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import EvidenceExposure, LearnerUnitState, Profile
from src.owner import Owner
from src.pipeline.engine import HadithRef, LearnerContext, QuranRef

# The engine is told about this many of the latest texts at most.
HISTORY_LIMIT = 200


async def _profile(db: AsyncSession, owner: Owner) -> Profile | None:
    if owner.user_id is None:
        return None
    return await db.get(Profile, owner.user_id)


async def memory_enabled(db: AsyncSession, owner: Owner) -> bool:
    """Whether the owner lets the app remember what it learnt (a guest always does)."""
    profile = await _profile(db, owner)
    return profile is None or profile.memory_enabled


async def learner_context(db: AsyncSession, owner: Owner) -> LearnerContext:
    """Return the context the engine receives for this owner."""
    profile = await _profile(db, owner)
    values: dict[str, object] = {}
    if profile is not None:
        values["personalization_enabled"] = profile.personalization_enabled
        if profile.personalization_enabled:
            values |= {
                "goals": list(profile.goals),
                "knowledge_level": str(profile.knowledge_level),
                "age_range": str(profile.age_range),
                "religious_background": str(profile.religious_background),
            }
    if profile is None or profile.memory_enabled:
        values |= await _history(db, owner)
    return LearnerContext.model_validate(values)


async def _history(db: AsyncSession, owner: Owner) -> dict[str, object]:
    exposures = (
        await db.scalars(
            select(EvidenceExposure)
            .where(owner.where(EvidenceExposure))
            .order_by(EvidenceExposure.at.desc())
            .limit(HISTORY_LIMIT)
        )
    ).all()
    quran: list[QuranRef] = []
    hadith: list[HadithRef] = []
    for row in exposures:
        if row.quran_surah is not None and row.quran_ayah is not None:
            ref = QuranRef(surah=row.quran_surah, ayah=row.quran_ayah)
            if ref not in quran:
                quran.append(ref)
        if row.hadith_collection is not None and row.hadith_number is not None:
            found = HadithRef(collection=row.hadith_collection, number=row.hadith_number)
            if found not in hadith:
                hadith.append(found)
    units = (
        await db.scalars(
            select(LearnerUnitState.unit_id)
            .where(owner.where(LearnerUnitState), LearnerUnitState.completed_count > 0)
            .order_by(LearnerUnitState.unit_id)
        )
    ).all()
    return {"seen_quran": quran, "seen_hadith": hadith, "completed_units": list(units)}


async def record_completion(
    db: AsyncSession,
    owner: Owner,
    *,
    unit_id: str | None,
    path_version: str | None,
    at: datetime,
) -> None:
    """Count one completion of a unit for the owner (a row is made on first use)."""
    if unit_id is None or path_version is None:
        return
    statement = insert(LearnerUnitState).values(
        **owner.columns(),
        path_version=path_version,
        unit_id=unit_id,
        completed_count=1,
        created_at=at,
        last_at=at,
    )
    column = LearnerUnitState.user_id if owner.user_id is not None else LearnerUnitState.guest_key
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=[column, LearnerUnitState.path_version, LearnerUnitState.unit_id],
            index_where=column.is_not(None),
            set_={
                "completed_count": LearnerUnitState.completed_count + 1,
                "last_at": at,
            },
        )
    )


def exposure(
    owner: Owner,
    *,
    kind: str,
    at: datetime,
    insight_id: object,
    quran: QuranRef | None,
    hadith: HadithRef | None,
    concept: str | None,
    unit_id: str | None,
) -> EvidenceExposure:
    """Return the exposure row of what a learner completed or found."""
    return EvidenceExposure(
        **owner.columns(),
        at=at,
        insight_id=insight_id,
        kind=kind,
        quran_surah=quran.surah if quran else None,
        quran_ayah=quran.ayah if quran else None,
        hadith_collection=hadith.collection if hadith else None,
        hadith_number=hadith.number if hadith else None,
        concept=(concept or "")[:80] or None,
        learning_unit_id=unit_id,
    )
