"""
InsightPlanner: up to three candidate insights for a scene, with the concepts to search for.

The planner (a chat model, structured output) reads the verified scene, the
ontology's candidate concepts with their constraints, the units of the
learning path that fit, and what the learner chose to share. It proposes
candidates: a concept, a value, the relation it has to the scene (v2 §8), the
entities and actions it rests on, and short Arabic queries for the Quran and
the hadiths. It never writes scripture: every field goes through the leak
guard, and an answer that leaks is asked again within the stage's bound.

The server does not take the plan on trust (master prompt v2 §8, masar §10.3):
unknown ids are dropped; a relation stronger than the scene supports is
lowered (`direct` needs an entity that is seen or confirmed, `action_based` an
action that is); a candidate resting only on blocked or unanswered entities is
dropped; a unit outside the offered list is ignored; with a focus, only
candidates about it are kept.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from src.ai.client import ModelClient
from src.config import AiStage
from src.pipeline.engine import EngineRequest, LearnerContext, RelationType
from src.pipeline.insight.context import SceneContext
from src.pipeline.insight.learning import UnitOption
from src.pipeline.leak_guard import LeakGuard, ScriptureLeakError
from src.pipeline.prompt import load_prompt
from src.pipeline.schemas import EvidenceStatus, SceneAnalysis

SYSTEM_PROMPT = "insight_planner_system.v1"
MAX_OUTPUT_TOKENS = 4096
MAX_QUERIES = 3
MIN_QUERY_WORDS = 1
MAX_QUERY_WORDS = 12
SHOWN = frozenset({EvidenceStatus.OBSERVED, EvidenceStatus.USER_CONFIRMED})

RelationName = Literal[
    "direct", "action_based", "close_conceptual", "opposite", "thematic_reminder"
]
ContentLevel = Literal["a", "b", "c", "d"]


def _says(text: str) -> Any:
    return Field(description=text)


class PlannedInsight(BaseModel):
    """One candidate insight, without any scripture text."""

    title: Annotated[str, _says("Arabic, two to five words.")]
    glimpse: Annotated[str, _says("Arabic, one short sentence.")]
    entity_ids: Annotated[list[str], _says("Scene entity ids the insight rests on.")]
    action_ids: Annotated[list[str], _says("Scene action ids it rests on; empty if none.")]
    concept: Annotated[str, _says("Arabic concept, a few words.")]
    value: Annotated[str, _says("Arabic value, a few words.")]
    relation: RelationName
    quran_queries: Annotated[list[str], _says("1-3 short Arabic concept phrases.")]
    hadith_queries: Annotated[list[str], _says("0-3 short Arabic concept phrases.")]
    ontology_entity_ids: Annotated[list[str], _says("Ontology ids (E...) used.")]
    learning_unit_id: Annotated[str | None, _says("One of the offered unit ids, or null.")]
    content_level: ContentLevel
    visible_clues: Annotated[list[str], _says("Arabic: what in the photo it rests on.")]
    limits: Annotated[list[str], _says("Arabic: what the photo does not allow saying.")]


class PlannerOutput(BaseModel):
    insights: list[PlannedInsight]
    needs_clarification: bool
    clarification_question: Annotated[str | None, _says("One short Arabic question, or null.")]
    unknown_concepts: Annotated[list[str], _says("Arabic concepts no ontology candidate holds.")]


@dataclass(frozen=True, slots=True)
class PlannedCandidate:
    """A candidate the server accepted, with its relation as the scene supports it."""

    title: str
    glimpse: str
    concept: str
    value: str
    relation: RelationType
    entity_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    quran_queries: tuple[str, ...]
    hadith_queries: tuple[str, ...]
    ontology_ids: tuple[str, ...]
    unit: UnitOption | None
    content_level: str
    visible_clues: tuple[str, ...]
    limits: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Plan:
    candidates: list[PlannedCandidate]
    question: str | None
    unknown_concepts: list[str]
    # Why candidates were dropped, for the scan trace.
    dropped: list[str]
    # Ids of entities a dropped candidate needed answered: their question may be asked.
    waiting_on: list[str]
    prompt_version: str


@dataclass(frozen=True, slots=True)
class FailedSearch:
    """A candidate whose queries found no reliable evidence, for a refinement round."""

    concept: str
    relation: RelationType
    queries: tuple[str, ...]


class PlannerLeakError(RuntimeError):
    """The planner kept writing scripture-like text after every attempt."""


def _clean(items: Sequence[str]) -> tuple[str, ...]:
    return tuple(item.strip() for item in items if item.strip())


def _queries(items: Sequence[str]) -> tuple[str, ...]:
    kept = [
        item.strip() for item in items if MIN_QUERY_WORDS <= len(item.split()) <= MAX_QUERY_WORDS
    ]
    return tuple(dict.fromkeys(kept))[:MAX_QUERIES]


def planner_texts(output: PlannerOutput) -> dict[str, str]:
    """Every free text of a plan, keyed by where it is, for the leak guard."""
    texts: dict[str, str] = {}
    if output.clarification_question:
        texts["clarification_question"] = output.clarification_question
    texts |= {f"unknown_concepts.{i}": text for i, text in enumerate(output.unknown_concepts)}
    for index, item in enumerate(output.insights):
        prefix = f"insights.{index}"
        texts |= {
            f"{prefix}.title": item.title,
            f"{prefix}.glimpse": item.glimpse,
            f"{prefix}.concept": item.concept,
            f"{prefix}.value": item.value,
        }
        for name in ("quran_queries", "hadith_queries", "visible_clues", "limits"):
            texts |= {f"{prefix}.{name}.{i}": text for i, text in enumerate(getattr(item, name))}
    return texts


def learner_payload(learner: LearnerContext) -> dict[str, Any]:
    """Return what the learner shared, without its history and its `unknown` fields."""
    shared = {
        "knowledge_level": learner.knowledge_level,
        "age_range": learner.age_range,
        "religious_background": learner.religious_background,
    }
    payload: dict[str, Any] = {key: value for key, value in shared.items() if value != "unknown"}
    if learner.goals:
        payload["goals"] = list(learner.goals)
    return payload


def scene_payload(scene: SceneAnalysis) -> dict[str, Any]:
    return {
        "description": scene.description,
        "entities": [
            {"id": e.id, "label": e.label_arabic, "status": e.status.value} for e in scene.entities
        ],
        "actions": [
            {
                "id": a.id,
                "label": a.label,
                "actors": a.actor_ids,
                "targets": a.target_ids,
                "clues": a.visible_evidence,
                "status": a.status.value,
            }
            for a in scene.actions
        ],
        "relations": [
            {"subject": r.subject_id, "predicate": r.predicate, "object": r.object_id}
            for r in scene.relations
        ],
        "ambiguities": scene.ambiguities,
    }


def user_message(
    request: EngineRequest,
    context: SceneContext,
    options: Sequence[UnitOption],
    refine: Sequence[FailedSearch],
) -> str:
    payload: dict[str, Any] = {
        "scene": scene_payload(request.scene),
        "focus": request.focus_entity_id,
        "clarification_answer": request.clarification_answer,
        "ontology": [
            {
                "entity_id": item.entity_id,
                "label": item.label,
                "candidates": [
                    {"id": candidate.entity_id, "label": candidate.label_ar}
                    for candidate in item.resolution.candidates[:3]
                ],
                "concepts": item.concepts(),
            }
            for item in context.entities.values()
        ],
        "forbidden": context.rules,
        "needs_answer": sorted(context.to_clarify),
        "learning_units": [
            {
                "id": option.unit.unit_id,
                "title": option.unit.title,
                "completed": option.completed,
                "ready": option.ready,
            }
            for option in options
        ],
        "learner": learner_payload(request.learner)
        if request.learner.personalization_enabled
        else {},
    }
    if refine:
        payload["refine"] = [
            {"concept": item.concept, "relation": item.relation.value, "queries": item.queries}
            for item in refine
        ]
    return json.dumps(payload, ensure_ascii=False)


def _lowered(item: PlannedInsight, scene: SceneAnalysis) -> RelationType:
    """Return the planner's relation, lowered to what the scene supports."""
    relation = RelationType(item.relation)
    entities = {entity.id: entity for entity in scene.entities}
    actions = {action.id: action for action in scene.actions}
    if relation is RelationType.ACTION_BASED and not any(
        actions[action_id].status in SHOWN for action_id in item.action_ids if action_id in actions
    ):
        return RelationType.CLOSE_CONCEPTUAL
    if relation is RelationType.DIRECT and not any(
        entities[entity_id].status in SHOWN
        for entity_id in item.entity_ids
        if entity_id in entities
    ):
        return RelationType.CLOSE_CONCEPTUAL
    return relation


class InsightPlanner:
    """Plans candidate insights with the provider's planner model."""

    def __init__(self, client: ModelClient, *, attempts: int = 2) -> None:
        self._client = client
        self._attempts = attempts

    async def plan(
        self,
        request: EngineRequest,
        context: SceneContext,
        options: Sequence[UnitOption],
        guard: LeakGuard,
        refine: Sequence[FailedSearch] = (),
    ) -> Plan:
        """Ask for a plan, refuse leaking answers within the bound, then check it against the scene."""
        system = load_prompt(SYSTEM_PROMPT)
        user = user_message(request, context, options, refine)
        for attempt in range(1, self._attempts + 1):
            result = await self._client.chat_json(
                PlannerOutput,
                stage=AiStage.PLANNER,
                system=system.render(max_insights=request.max_insights),
                user=user,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            )
            try:
                guard.ensure_clean(planner_texts(result.value))
            except ScriptureLeakError as error:
                if attempt == self._attempts:
                    raise PlannerLeakError(str(error)) from None
                continue
            return self._checked(result.value, request, context, options, system.version)
        raise AssertionError  # the loop returns or raises

    def _checked(
        self,
        output: PlannerOutput,
        request: EngineRequest,
        context: SceneContext,
        options: Sequence[UnitOption],
        version: str,
    ) -> Plan:
        scene = request.scene
        entity_ids = {entity.id for entity in scene.entities}
        action_ids = {action.id for action in scene.actions}
        units = {option.unit.unit_id: option for option in options}
        ontology_ids = {
            candidate.entity_id
            for item in context.entities.values()
            for candidate in item.resolution.candidates
        }
        kept: list[PlannedCandidate] = []
        dropped: list[str] = []
        waiting: list[str] = []
        for index, item in enumerate(output.insights[: request.max_insights]):
            entities = tuple(e for e in dict.fromkeys(item.entity_ids) if e in entity_ids)
            actions = tuple(a for a in dict.fromkeys(item.action_ids) if a in action_ids)
            quran, hadith = _queries(item.quran_queries), _queries(item.hadith_queries)
            reason = None
            if request.focus_entity_id and request.focus_entity_id not in entities:
                reason = "not about the focus"
            elif context.unusable(entities):
                reason = "rests only on blocked or unanswered entities"
                waiting += [e for e in entities if e in context.to_clarify]
            elif not quran and not hadith:
                reason = "no usable query"
            if reason:
                dropped.append(f"candidate {index}: {reason}")
                continue
            kept.append(
                PlannedCandidate(
                    title=item.title.strip(),
                    glimpse=item.glimpse.strip(),
                    concept=item.concept.strip(),
                    value=item.value.strip(),
                    relation=_lowered(item, scene),
                    entity_ids=entities,
                    action_ids=actions,
                    quran_queries=quran,
                    hadith_queries=hadith,
                    ontology_ids=tuple(i for i in item.ontology_entity_ids if i in ontology_ids),
                    unit=units.get(item.learning_unit_id or ""),
                    content_level=item.content_level,
                    visible_clues=_clean(item.visible_clues),
                    limits=_clean(item.limits),
                )
            )
        question = (output.clarification_question or "").strip() or None
        return Plan(
            candidates=kept,
            question=question if output.needs_clarification else None,
            unknown_concepts=list(_clean(output.unknown_concepts)),
            dropped=dropped,
            waiting_on=waiting,
            prompt_version=version,
        )
