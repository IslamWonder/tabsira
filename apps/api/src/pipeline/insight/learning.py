"""
The learning path's part in an insight (masar §10): which units fit the scene, and the next move.

The path is data (`learning_units` of the active version). The units whose
title, objectives and concepts share stems with what the scene shows are
offered to the planner, each with whether the learner completed it and
whether its prerequisites are met; the planner may tie an insight to one of
them, never to a unit outside the list. The path only chooses among correct
meanings: it never adds an action, a relation or a text to a scene (masar
§10.3), and a unit's anchors are only retrieval hints («مراجع الارتكاز»).

Among insights that passed the evidence gate, the order follows masar §10.4:
the learner's focus, then the strength of the relation, then a unit whose
prerequisites are ready and that is not completed yet (the next step), then
new texts over texts already seen, then a domain the learner has seen less.
Misconceptions are not recorded yet, so that criterion is left out; with
personalisation off, nothing of the learner's history is used (§10.5: no
invented history).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.messages import messages_for
from src.models import LearningPathVersion, LearningUnit
from src.pipeline.engine import LearnerContext, RelationType
from src.retrieval.query import query_terms

UNIT_OPTIONS = 8
# Relation types from the strongest (0) down, as the ladder of v2 §8 orders them.
RELATION_ORDER = {relation: rank for rank, relation in enumerate(RelationType)}


@dataclass(frozen=True, slots=True)
class Unit:
    unit_id: str
    domain_id: str
    title: str
    concepts: tuple[str, ...]
    prerequisites: tuple[str, ...]
    anchors: tuple[str, ...]
    stems: frozenset[str]


@dataclass(frozen=True, slots=True)
class LearningPath:
    version: str
    units: dict[str, Unit]


@dataclass(frozen=True, slots=True)
class UnitOption:
    """A unit offered to the planner for this scene and this learner."""

    unit: Unit
    completed: bool
    ready: bool
    match: int


def _stems(texts: Sequence[str]) -> frozenset[str]:
    return frozenset(term for text in texts for term in query_terms(text))


async def load_path(session: AsyncSession) -> LearningPath | None:
    """Return the active version of the learning path, or None when none is imported."""
    version = await session.scalar(
        select(LearningPathVersion.path_version).where(LearningPathVersion.is_active.is_(True))
    )
    if version is None:
        return None
    rows = await session.scalars(
        select(LearningUnit).where(LearningUnit.path_version == version).order_by(LearningUnit.id)
    )
    units = {
        row.id: Unit(
            unit_id=row.id,
            domain_id=row.domain_id,
            title=row.title,
            concepts=tuple(row.concepts),
            prerequisites=tuple(row.prerequisites),
            anchors=tuple(row.source_anchors),
            stems=_stems([row.title, *row.objectives, *row.concepts]),
        )
        for row in rows
    }
    return LearningPath(version, units)


def completed_units(learner: LearnerContext) -> frozenset[str]:
    """Return the units the learner completed, or none when personalisation is off."""
    return frozenset(learner.completed_units) if learner.personalization_enabled else frozenset()


def unit_options(
    path: LearningPath, scene_texts: Sequence[str], learner: LearnerContext
) -> list[UnitOption]:
    """Return the units that share the most stems with the scene, best first."""
    wanted = _stems(scene_texts)
    done = completed_units(learner)
    scored = [
        UnitOption(
            unit=unit,
            completed=unit.unit_id in done,
            ready=all(prerequisite in done for prerequisite in unit.prerequisites),
            match=sum(1 for stem in unit.stems if any(stem.startswith(w) for w in wanted)),
        )
        for unit in path.units.values()
    ]
    found = [option for option in scored if option.match > 0]
    found.sort(key=lambda option: (-option.match, option.unit.unit_id))
    return found[:UNIT_OPTIONS]


@dataclass(frozen=True, slots=True)
class RankedInsight:
    """What masar §10.4 weighs, for one insight that passed the gate."""

    on_focus: bool
    relation: RelationType
    unit: UnitOption | None
    new_texts: int
    domain_seen: int


def rank_key(item: RankedInsight) -> tuple[int, int, int, int, int]:
    """Sort key: focus, relation strength, next step, new texts, less covered domain."""
    next_step = 0 if item.unit is not None and item.unit.ready and not item.unit.completed else 1
    return (
        0 if item.on_focus else 1,
        RELATION_ORDER[item.relation],
        next_step,
        -item.new_texts,
        item.domain_seen,
    )


def domain_counts(path: LearningPath, learner: LearnerContext) -> Counter[str]:
    """How many completed units the learner has in each domain."""
    return Counter(
        path.units[unit_id].domain_id
        for unit_id in completed_units(learner)
        if unit_id in path.units
    )


def personalised_reason(
    option: UnitOption | None, learner: LearnerContext, *, review: bool, new_text: bool
) -> str | None:
    """Return the honest «why this for me» line, or None when nothing of the learner was used."""
    if not learner.personalization_enabled:
        return None
    text = messages_for()
    reasons = (
        (review, text.engine_reason_review),
        (new_text, text.engine_reason_new_text),
        (
            option is not None and option.completed,
            text.engine_reason_deeper.format(unit=option.unit.title if option else ""),
        ),
        (
            option is not None and bool(option.unit.prerequisites) and option.ready,
            text.engine_reason_next_step,
        ),
        (not learner.completed_units, text.engine_reason_first_steps),
    )
    return next((reason for applies, reason in reasons if applies), None)
