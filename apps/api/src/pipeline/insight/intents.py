"""
SemanticIntentPlanner: the meanings a scene supports, as search intents, before any text is chosen.

The planner (a chat model, structured output) reads the verified scene, the
ontology's candidate concepts and their constraints, and proposes search
intents («نوايا بحث»): each rests on named scene clues, states the observable
meaning in neutral words, the concept to test and its basis, what is uncertain
and what must not be assumed, and the queries of each corpus in two kinds:
lexical (keywords for full text and concept search) and semantic (one natural
sentence for the vector search). It decides no insight: a title, a value and
an explanation are written only after the evidence has been verified. It
never sees the learner's profile or history, and never writes scripture:
every field goes through the leak guard, and an answer that leaks is asked
again within the stage's bound.

The server does not take the plan on trust: unknown ids are dropped; a relation
stronger than the scene supports is lowered (`direct` needs an entity that is
seen or confirmed, `action_based` an action that is); an intent resting only on
blocked or unanswered entities is dropped; with a focus, only intents about it
are kept; in a refinement round an intent must keep the anchors of a failed
one, so a search is never widened to a new topic to fill a gap.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from src.ai.client import ModelClient
from src.config import AiStage
from src.models import EmbeddedCorpus
from src.pipeline.engine import EngineRequest, RelationType
from src.pipeline.insight.context import SceneContext
from src.pipeline.insight.guard import EngineGuard
from src.pipeline.leak_guard import ScriptureLeakError
from src.pipeline.prompt import load_prompt
from src.pipeline.schemas import EvidenceStatus, SceneAnalysis

SYSTEM_PROMPT = "intent_planner_system.v1"
MAX_OUTPUT_TOKENS = 3000
# Intents a plan may carry: a scene rarely supports more distinct meanings honestly.
MAX_INTENTS = 4
MAX_LEXICAL = 3
MAX_SEMANTIC = 2
LEXICAL_WORDS = (1, 8)
SEMANTIC_WORDS = (3, 30)
SHOWN = frozenset({EvidenceStatus.OBSERVED, EvidenceStatus.USER_CONFIRMED})

RelationName = Literal["direct", "action_based", "close_conceptual", "opposite"]
ContentLevel = Literal["a", "b", "c", "d"]


def _says(text: str) -> Any:
    return Field(description=text)


class CorpusQueries(BaseModel):
    lexical: Annotated[list[str], _says("1-3 Arabic keyword queries, 2-6 words each.")]
    semantic: Annotated[list[str], _says("1-2 natural Arabic sentences, one meaning each.")]


class PlannedIntent(BaseModel):
    """One search intent, without any scripture text and without any decided insight."""

    scene_anchor_ids: Annotated[list[str], _says("Scene entity and action ids it rests on.")]
    observable_meaning: Annotated[str, _says("Arabic: what the clues support, neutrally.")]
    relation_description: Annotated[
        str | None, _says("Arabic: the central action or relation, or null.")
    ]
    candidate_concept: Annotated[str, _says("Arabic concept to test, a few words.")]
    concept_basis: Annotated[str, _says("Arabic: one sentence linking concept and clues.")]
    relation: RelationName
    content_level: ContentLevel
    uncertainties: Annotated[list[str], _says("Arabic: what the photo leaves unsettled.")]
    unsupported_assumptions: Annotated[list[str], _says("Arabic: what must not be assumed.")]
    quran: CorpusQueries
    hadith: CorpusQueries
    ontology_entity_ids: Annotated[list[str], _says("Ontology ids (E...) used.")]


class IntentPlanOutput(BaseModel):
    intents: list[PlannedIntent]
    needs_clarification: bool
    clarification_question: Annotated[str | None, _says("One short Arabic question, or null.")]
    unknown_concepts: Annotated[list[str], _says("Arabic concepts no ontology candidate holds.")]


@dataclass(frozen=True, slots=True)
class IntentQueries:
    """The queries of one corpus: keywords for the lexical lists, sentences for the vectors."""

    lexical: tuple[str, ...]
    semantic: tuple[str, ...]

    @property
    def empty(self) -> bool:
        return not self.lexical and not self.semantic


@dataclass(frozen=True, slots=True)
class SearchIntent:
    """An intent the server accepted, with its relation as the scene supports it."""

    intent_id: str
    entity_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    observable_meaning: str
    relation_description: str | None
    candidate_concept: str
    concept_basis: str
    relation: RelationType
    content_level: str
    uncertainties: tuple[str, ...]
    unsupported_assumptions: tuple[str, ...]
    queries: dict[EmbeddedCorpus, IntentQueries]
    ontology_ids: tuple[str, ...]

    @property
    def anchor_ids(self) -> frozenset[str]:
        return frozenset((*self.entity_ids, *self.action_ids))

    def queries_of(self, corpus: EmbeddedCorpus) -> IntentQueries:
        return self.queries[corpus]

    def as_trace(self) -> dict[str, Any]:
        """Return the intent for the scan trace: its server id, anchors, guarded words and queries."""
        return {
            "intent_id": self.intent_id,
            "anchors": sorted(self.anchor_ids),
            "concept": self.candidate_concept,
            "relation": self.relation.value,
            "queries": {
                corpus.value: {"lexical": list(q.lexical), "semantic": list(q.semantic)}
                for corpus, q in self.queries.items()
            },
        }


@dataclass(frozen=True, slots=True)
class IntentPlan:
    intents: list[SearchIntent]
    question: str | None
    unknown_concepts: list[str]
    # Why intents were dropped, for the scan trace.
    dropped: list[str]
    # Ids of entities a dropped intent needed answered: their question may be asked.
    waiting_on: list[str]
    prompt_version: str


@dataclass(frozen=True, slots=True)
class FailedIntent:
    """An intent whose searches found no accepted text, with the reasons, for a refinement."""

    intent: SearchIntent
    # Reject reasons of the verifier, most frequent first, or the search outcome.
    reasons: tuple[str, ...]


class PlannerLeakError(RuntimeError):
    """The planner kept writing scripture-like text after every attempt."""


def _clean(items: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.strip() for item in items if item.strip()))


def _queries(items: Sequence[str], words: tuple[int, int], limit: int) -> tuple[str, ...]:
    low, high = words
    kept = [item.strip() for item in items if low <= len(item.split()) <= high]
    return tuple(dict.fromkeys(kept))[:limit]


def corpus_queries(given: CorpusQueries) -> IntentQueries:
    return IntentQueries(
        lexical=_queries(given.lexical, LEXICAL_WORDS, MAX_LEXICAL),
        semantic=_queries(given.semantic, SEMANTIC_WORDS, MAX_SEMANTIC),
    )


def planner_texts(output: IntentPlanOutput) -> dict[str, str]:
    """Every free text of a plan, keyed by where it is, for the leak guard."""
    texts: dict[str, str] = {}
    if output.clarification_question:
        texts["clarification_question"] = output.clarification_question
    texts |= {f"unknown_concepts.{i}": text for i, text in enumerate(output.unknown_concepts)}
    for index, item in enumerate(output.intents):
        prefix = f"intents.{index}"
        texts |= {
            f"{prefix}.observable_meaning": item.observable_meaning,
            f"{prefix}.candidate_concept": item.candidate_concept,
            f"{prefix}.concept_basis": item.concept_basis,
        }
        if item.relation_description:
            texts[f"{prefix}.relation_description"] = item.relation_description
        for name in ("uncertainties", "unsupported_assumptions"):
            texts |= {f"{prefix}.{name}.{i}": text for i, text in enumerate(getattr(item, name))}
        for corpus in ("quran", "hadith"):
            queries: CorpusQueries = getattr(item, corpus)
            texts |= {f"{prefix}.{corpus}.lexical.{i}": t for i, t in enumerate(queries.lexical)}
            texts |= {f"{prefix}.{corpus}.semantic.{i}": t for i, t in enumerate(queries.semantic)}
    return texts


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
    request: EngineRequest, context: SceneContext, refine: Sequence[FailedIntent]
) -> str:
    """Assemble what the planner reads: the scene and the ontology, never the learner."""
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
    }
    if refine:
        payload["refine"] = [
            {
                "intent_id": failed.intent.intent_id,
                "scene_anchor_ids": sorted(failed.intent.anchor_ids),
                "observable_meaning": failed.intent.observable_meaning,
                "candidate_concept": failed.intent.candidate_concept,
                "queries": {
                    corpus.value: {"lexical": list(q.lexical), "semantic": list(q.semantic)}
                    for corpus, q in failed.intent.queries.items()
                },
                "rejected_because": list(failed.reasons),
            }
            for failed in refine
        ]
    return json.dumps(payload, ensure_ascii=False)


def _participants(scene: SceneAnalysis, action_ids: Sequence[str]) -> tuple[str, ...]:
    """Return the actors and targets of these actions, in scene order, once each."""
    wanted = set(action_ids)
    return tuple(
        dict.fromkeys(
            entity_id
            for action in scene.actions
            if action.id in wanted
            for entity_id in (*action.actor_ids, *action.target_ids)
        )
    )


def _lowered(item: PlannedIntent, scene: SceneAnalysis) -> RelationType:
    """Return the planner's relation, lowered to what the scene supports."""
    relation = RelationType(item.relation)
    entities = {entity.id: entity for entity in scene.entities}
    actions = {action.id: action for action in scene.actions}
    anchors = item.scene_anchor_ids
    if relation is RelationType.ACTION_BASED and not any(
        actions[anchor].status in SHOWN for anchor in anchors if anchor in actions
    ):
        return RelationType.CLOSE_CONCEPTUAL
    if relation is RelationType.DIRECT and not any(
        entities[anchor].status in SHOWN for anchor in anchors if anchor in entities
    ):
        return RelationType.CLOSE_CONCEPTUAL
    return relation


class SemanticIntentPlanner:
    """Plans search intents with the provider's planner model."""

    def __init__(self, client: ModelClient, *, attempts: int = 2) -> None:
        self._client = client
        self._attempts = attempts

    async def plan(
        self,
        request: EngineRequest,
        context: SceneContext,
        guard: EngineGuard,
        refine: Sequence[FailedIntent] = (),
        id_prefix: str = "i",
    ) -> IntentPlan:
        """
        Ask for a plan, refuse leaking answers within the bound, then check it against the scene.

        Intents are named by the server (`i1`, `i2`, or `r1i1` in a refinement round): the model
        writes no id, so the trace holds none of its words unguarded.
        """
        system = load_prompt(SYSTEM_PROMPT)
        user = user_message(request, context, refine)
        for attempt in range(1, self._attempts + 1):
            result = await self._client.chat_json(
                IntentPlanOutput,
                stage=AiStage.PLANNER,
                system=system.text,
                user=user,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            )
            try:
                await guard.ensure_clean(planner_texts(result.value))
            except ScriptureLeakError as error:
                if attempt == self._attempts:
                    raise PlannerLeakError(str(error)) from None
                continue
            return self._checked(result.value, request, context, refine, system.version, id_prefix)
        raise AssertionError  # the loop returns or raises

    def _checked(
        self,
        output: IntentPlanOutput,
        request: EngineRequest,
        context: SceneContext,
        refine: Sequence[FailedIntent],
        version: str,
        id_prefix: str,
    ) -> IntentPlan:
        scene = request.scene
        entity_ids = {entity.id for entity in scene.entities}
        action_ids = {action.id for action in scene.actions}
        ontology_ids = {
            candidate.entity_id
            for item in context.entities.values()
            for candidate in item.resolution.candidates
        }
        allowed_anchors = {failed.intent.anchor_ids for failed in refine}
        kept: list[SearchIntent] = []
        dropped: list[str] = []
        waiting: list[str] = []
        for index, item in enumerate(output.intents[:MAX_INTENTS]):
            anchors = list(dict.fromkeys(item.scene_anchor_ids))
            entities = tuple(a for a in anchors if a in entity_ids)
            actions = tuple(a for a in anchors if a in action_ids)
            if not entities and actions:
                # An intent anchored on an action alone rests on that action's participants.
                entities = _participants(scene, actions)
            queries = {
                EmbeddedCorpus.QURAN: corpus_queries(item.quran),
                EmbeddedCorpus.HADITH: corpus_queries(item.hadith),
            }
            reason = None
            if request.focus_entity_id and request.focus_entity_id not in entities:
                reason = "not about the focus"
            elif context.unusable(entities):
                reason = "rests only on blocked or unanswered entities"
                waiting += [e for e in entities if e in context.to_clarify]
            elif all(q.empty for q in queries.values()):
                reason = "no usable query"
            elif refine and frozenset((*entities, *actions)) not in allowed_anchors:
                reason = "refinement moved to other clues"
            if reason:
                dropped.append(f"intent {index}: {reason}")
                continue
            kept.append(
                SearchIntent(
                    intent_id=f"{id_prefix}{len(kept) + 1}",
                    entity_ids=entities,
                    action_ids=actions,
                    observable_meaning=item.observable_meaning.strip(),
                    relation_description=(item.relation_description or "").strip() or None,
                    candidate_concept=item.candidate_concept.strip(),
                    concept_basis=item.concept_basis.strip(),
                    relation=_lowered(item, scene),
                    content_level=item.content_level,
                    uncertainties=_clean(item.uncertainties),
                    unsupported_assumptions=_clean(item.unsupported_assumptions),
                    queries=queries,
                    ontology_ids=tuple(i for i in item.ontology_entity_ids if i in ontology_ids),
                )
            )
        question = (output.clarification_question or "").strip() or None
        return IntentPlan(
            intents=kept,
            question=question if output.needs_clarification else None,
            unknown_concepts=list(_clean(output.unknown_concepts)),
            dropped=dropped,
            waiting_on=waiting,
            prompt_version=version,
        )
