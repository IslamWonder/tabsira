"""
The hidden treasure (v2 §17): chosen from verified candidates only, shown only on return.

Candidates come from the learning path, never from a search made for the
occasion: first the other source anchors of the completed insight's own unit
(another text of the same weight), then the anchors of the units of the same
domain that name this unit as their prerequisite (a deeper meaning on the same
road). A candidate is kept only when the store holds its text, a hadith only
when no editor ruled it out (decision 64), and never a text the insight showed or
the learner has already met. A range of verses is skipped: a treasure is one
whole text. An insight with no valid candidate gets no treasure.

The treasure stays hidden until the learner comes back (`treasure_ready`):
after TREASURE_REVEAL_AFTER_DAYS, on a visit to its place at least
TREASURE_RETURN_AFTER_HOURS after it was hidden, or once a related insight
(same place, same unit or same concept) was completed after it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Hadith, LearningUnit, QuranVerse, TreasureKind
from src.pipeline.engine import HadithRef, QuranRef
from src.scripture.rulings import is_eligible

_QURAN_ANCHOR = re.compile(r"^Q:(\d{1,3}):(\d{1,3})$")
_HADITH_ANCHOR = re.compile(r"^H:([a-z]{2,32}):([0-9A-Za-z.]{1,32})$")

Reference = QuranRef | HadithRef


@dataclass(frozen=True)
class UnitInfo:
    id: str
    domain_id: str
    position: int
    prerequisites: tuple[str, ...]
    anchors: tuple[str, ...]


@dataclass(frozen=True)
class Candidate:
    kind: TreasureKind
    ref: Reference
    unit_id: str


def parse_anchor(anchor: str) -> Reference | None:
    """Read `Q:30:50` or `H:bukhari:2320`; None for a range, a note or anything else."""
    quran = _QURAN_ANCHOR.match(anchor)
    if quran:
        surah, ayah = int(quran.group(1)), int(quran.group(2))
        if 1 <= surah <= 114 and 1 <= ayah <= 286:
            return QuranRef(surah=surah, ayah=ayah)
        return None
    hadith = _HADITH_ANCHOR.match(anchor)
    if hadith:
        return HadithRef(collection=hadith.group(1), number=hadith.group(2))
    return None


def _refs(unit: UnitInfo) -> list[Reference]:
    parsed = (parse_anchor(anchor) for anchor in unit.anchors)
    return [ref for ref in parsed if ref is not None]


def candidates(unit: UnitInfo, units: Sequence[UnitInfo]) -> list[Candidate]:
    """Return the candidates of a unit, in the order they are tried."""
    found = [Candidate(TreasureKind.ALTERNATIVE, ref, unit.id) for ref in _refs(unit)]
    deeper = sorted(
        (
            other
            for other in units
            if other.domain_id == unit.domain_id and unit.id in other.prerequisites
        ),
        key=lambda other: other.position,
    )
    for other in deeper:
        found += [Candidate(TreasureKind.DEEPER, ref, other.id) for ref in _refs(other)]
    return found


def treasure_ready(
    created_at: datetime,
    now: datetime,
    *,
    last_visit: datetime | None,
    related_completed_after: bool,
    reveal_after: timedelta,
    return_after: timedelta,
) -> bool:
    """Tell whether a hidden treasure may show: the learner has come back."""
    if now - created_at >= reveal_after:
        return True
    if last_visit is not None and last_visit - created_at >= return_after:
        return True
    return related_completed_after


async def unit_infos(db: AsyncSession, path_version: str) -> list[UnitInfo]:
    rows = await db.scalars(select(LearningUnit).where(LearningUnit.path_version == path_version))
    return [
        UnitInfo(
            id=row.id,
            domain_id=row.domain_id,
            position=row.position,
            prerequisites=tuple(row.prerequisites),
            anchors=tuple(row.source_anchors),
        )
        for row in rows
    ]


async def verified(db: AsyncSession, ref: Reference) -> bool:
    """Tell whether the store holds the text, and a hadith is eligible as evidence."""
    if isinstance(ref, QuranRef):
        found = await db.scalar(
            select(QuranVerse.id).where(QuranVerse.surah == ref.surah, QuranVerse.ayah == ref.ayah)
        )
        return found is not None
    hadith_id = await db.scalar(
        select(Hadith.id).where(Hadith.collection == ref.collection, Hadith.number == ref.number)
    )
    if hadith_id is None:
        return False
    return await is_eligible(db, hadith_id)


async def choose(
    db: AsyncSession,
    *,
    unit_id: str,
    path_version: str,
    excluded: Iterable[Reference],
) -> Candidate | None:
    """Return the first verified candidate of a unit that is not excluded, or None."""
    units = await unit_infos(db, path_version)
    unit = next((info for info in units if info.id == unit_id), None)
    if unit is None:
        return None
    skip = set(excluded)
    for candidate in candidates(unit, units):
        if candidate.ref not in skip and await verified(db, candidate.ref):
            return candidate
        skip.add(candidate.ref)
    return None
