"""
What the ontology says about a scene: candidate concepts per entity, and their constraints.

Every entity of the analysed scene is resolved (`OntologyResolver`) and the
special constraint of its best candidate is applied (`apply_constraint`):

- a BLOCK forbids an inference (a diagnosis, a person's identity). It is a hard
  stop: an insight resting only on blocked entities is never proposed, a scan
  focused on one stops, and the rule is given to every model stage;
- a CLARIFY asks something first. Its question becomes the scan's
  clarification question when the insight would rest on that entity alone; an
  action the scene shows, or an answer the person already gave, lifts it.

The ontology proposes concepts; it never proves a relation to a text.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from src.pipeline.schemas import EvidenceStatus, SceneAnalysis
from src.services.ontology_constraints import ConstraintAction, ConstraintOutcome, apply_constraint
from src.services.ontology_resolver import (
    LabelResolution,
    OntologyResolver,
    SceneLabel,
    SceneRelation,
)

# Candidate concepts of an entity shown to the planner.
CONCEPTS_PER_ENTITY = 6


@dataclass(frozen=True, slots=True)
class EntityContext:
    """One scene entity as the ontology sees it."""

    entity_id: str
    label: str
    resolution: LabelResolution
    constraint: ConstraintOutcome

    def concepts(self) -> list[str]:
        """Return the candidate entities' Arabic labels and the concepts the scene activated."""
        terms = [
            term
            for candidate in self.resolution.candidates[:3]
            for term in (candidate.label_ar, *candidate.activated)
        ]
        return list(dict.fromkeys(terms))[:CONCEPTS_PER_ENTITY]


@dataclass(frozen=True, slots=True)
class SceneContext:
    entities: dict[str, EntityContext]
    unresolved: list[LabelResolution] = field(default_factory=list)

    @property
    def blocked(self) -> frozenset[str]:
        return frozenset(
            entity_id
            for entity_id, item in self.entities.items()
            if item.constraint.action is ConstraintAction.BLOCK
        )

    @property
    def to_clarify(self) -> dict[str, ConstraintOutcome]:
        return {
            entity_id: item.constraint
            for entity_id, item in self.entities.items()
            if item.constraint.action is ConstraintAction.CLARIFY
        }

    @property
    def rules(self) -> list[str]:
        """The Arabic statements of every block, once each."""
        rules: list[str] = []
        for item in self.entities.values():
            rule = item.constraint.rule
            if rule and rule not in rules:
                rules.append(rule)
        return rules

    def unusable(self, entity_ids: Sequence[str]) -> bool:
        """Whether an insight on these entities rests only on blocked or unanswered ones."""
        known = [entity_id for entity_id in entity_ids if entity_id in self.entities]
        stuck = self.blocked | frozenset(self.to_clarify)
        return not known or all(entity_id in stuck for entity_id in known)

    def question_for(self, entity_ids: Sequence[str]) -> str | None:
        """Return the clarification question of the first of these entities that has one."""
        for entity_id in entity_ids:
            outcome = self.to_clarify.get(entity_id)
            if outcome is not None:
                return outcome.question
        return None


def _shown_actors(scene: SceneAnalysis) -> set[str]:
    """Entities that take part in an action the scene shows (observed or confirmed)."""
    shown = {EvidenceStatus.OBSERVED, EvidenceStatus.USER_CONFIRMED}
    return {
        entity_id
        for action in scene.actions
        if action.status in shown
        for entity_id in (*action.actor_ids, *action.target_ids)
    }


async def build_context(
    session: AsyncSession, scene: SceneAnalysis, *, clarified: bool
) -> SceneContext:
    """Resolve every entity of the scene and apply its constraint."""
    if not scene.entities:
        return SceneContext({})
    labels = {entity.id: entity.label_arabic or entity.label for entity in scene.entities}
    relations = [
        SceneRelation(labels[item.subject_id], item.predicate, labels[item.object_id])
        for item in scene.relations
        if item.subject_id in labels and item.object_id in labels
    ]
    resolutions = await OntologyResolver(session).resolve(
        [SceneLabel(entity.label, entity.label_arabic) for entity in scene.entities], relations
    )
    actors = _shown_actors(scene)
    entities = {
        entity.id: EntityContext(
            entity_id=entity.id,
            label=entity.label_arabic or entity.label,
            resolution=resolution,
            constraint=apply_constraint(
                resolution.best, confirmed=clarified, action_observed=entity.id in actors
            ),
        )
        for entity, resolution in zip(scene.entities, resolutions, strict=True)
    }
    unresolved = [resolution for resolution in resolutions if not resolution.resolved]
    return SceneContext(entities, unresolved)
