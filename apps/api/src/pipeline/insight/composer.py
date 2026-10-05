"""
The composer: the platform's own explanation of each insight («شرح تبصرة»), never the texts.

A chat model (structured output) writes the five parts of v2 §12 (what
appeared, the value, what the verse adds, what the hadith adds, life), the
concept of «لماذا ظهر هذا؟» and one small optional step, in Arabic adapted to
the learner's declared level. It sees the meaning of the chosen texts as
folded Arabic so it can explain them, and it cites them by reference only:
every field goes through the leak guard, whose corpus includes those texts,
and an answer that leaks is asked again within the stage's bound; an insight
whose text still leaks is dropped.

The server, not the model, decides what is shown: a part about a verse or a
hadith exists only when that text was chosen; a step is «من السنة» only when
the chosen hadith grounds it, otherwise it is a practical suggestion; a
personal matter (content level «د») ends with the referral to a qualified
scholar (v2 §12, rule 7).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from src.ai.client import ModelClient
from src.config import AiStage
from src.messages import messages_for
from src.pipeline.engine import (
    EvidenceRef,
    ExplanationPart,
    HadithRef,
    LearnerContext,
    ProposedInsight,
    QuranRef,
    RelationType,
    SmallStep,
    WhyThis,
)
from src.pipeline.insight.evidence import TEXT_CHARS, Chosen, GateResult
from src.pipeline.insight.guard import EngineGuard
from src.pipeline.insight.learning import personalised_reason
from src.pipeline.insight.planner import learner_payload
from src.pipeline.prompt import load_prompt
from src.pipeline.schemas import BBox, SceneAnalysis

SYSTEM_PROMPT = "insight_composer_system.v2"
# A part's sources name the insight's own texts (quran:S:A, hadith:C:N) or its unit.
UNIT_PREFIX = "masar:"
MAX_OUTPUT_TOKENS = 6000


class ComposedStep(BaseModel):
    text: str
    kind: Literal["text_grounded", "ethical_application", "reflection"]
    from_hadith: bool


class ComposedInsight(BaseModel):
    insight: Annotated[int, Field(description="The index of the insight given.")]
    title: str
    glimpse: str
    seen: str
    value: str
    quran: str | None
    sunnah: str | None
    life: str
    why_concept: str
    small_step: ComposedStep | None


class ComposerOutput(BaseModel):
    insights: list[ComposedInsight]


@dataclass(frozen=True, slots=True)
class Composition:
    insights: list[ProposedInsight]
    # Indexes of gate results whose text kept leaking and were dropped.
    leaked: list[int]
    prompt_version: str


def composer_texts(item: ComposedInsight) -> dict[str, str]:
    texts = {
        "title": item.title,
        "glimpse": item.glimpse,
        "seen": item.seen,
        "value": item.value,
        "life": item.life,
        "why_concept": item.why_concept,
    }
    texts |= {
        name: value for name, value in (("quran", item.quran), ("sunnah", item.sunnah)) if value
    }
    if item.small_step is not None:
        texts["small_step"] = item.small_step.text
    return texts


def composer_message(
    scene: SceneAnalysis, results: Sequence[GateResult], learner: LearnerContext
) -> str:
    learner_view = learner_payload(learner) if learner.personalization_enabled else {}
    payload: dict[str, Any] = {
        "scene": scene.description,
        "learner": {"level": learner_view.get("knowledge_level", "beginner"), **learner_view},
        "insights": [
            {
                "insight": index,
                "concept": result.candidate.concept,
                "value": result.candidate.value,
                "relation": result.relation.value,
                "content_level": result.candidate.content_level,
                "visible_clues": result.candidate.visible_clues,
                "limits": [
                    *result.candidate.limits,
                    *(c.limit for c in (result.quran, result.hadith) if c and c.limit),
                ],
                "verse_meaning": result.quran.found.document.text[:TEXT_CHARS]
                if result.quran
                else None,
                "hadith_meaning": result.hadith.found.document.text[:TEXT_CHARS]
                if result.hadith
                else None,
            }
            for index, result in enumerate(results)
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def _reference(chosen: Chosen | None, ref: QuranRef | HadithRef | None) -> EvidenceRef | None:
    if chosen is None or ref is None:
        return None
    # A text the verifier called weak is a general reminder on its own line too.
    weak = chosen.strength == "weak"
    return EvidenceRef(
        ref=ref,
        relation=RelationType.THEMATIC_REMINDER if weak else chosen.relation,
        retrieval_score=round(chosen.found.retrieval_score, 6),
        rerank_score=chosen.found.rerank_score,
        matched_on=chosen.found.matched_on,
    )


def citation(ref: QuranRef | HadithRef) -> str:
    """Return the reference a part or a step cites a text by: quran:S:A or hadith:C:N."""
    if isinstance(ref, QuranRef):
        return f"quran:{ref.surah}:{ref.ayah}"
    return f"hadith:{ref.collection}:{ref.number}"


def unit_citation(unit_id: str) -> str:
    return f"{UNIT_PREFIX}{unit_id}"


def allowed_references(insight: ProposedInsight) -> frozenset[str]:
    """Return what an insight may cite: its own texts and its own learning unit."""
    texts = {citation(e.ref) for e in (insight.quran, insight.hadith) if e is not None}
    unit = {unit_citation(insight.learning_unit_id)} if insight.learning_unit_id else set()
    return frozenset(texts | unit)


def cites_only_its_own(insight: ProposedInsight) -> bool:
    """Whether every source and grounding names the insight's own texts or unit, nothing else."""
    allowed = allowed_references(insight)
    sources = {source for part in insight.explanation for source in part.sources}
    grounded = set(insight.small_step.grounded_in) if insight.small_step else set()
    texts = {ref for ref in allowed if not ref.startswith(UNIT_PREFIX)}
    return sources <= allowed and grounded <= texts


def _step(item: ComposedInsight, result: GateResult) -> SmallStep | None:
    step = item.small_step
    if step is None or not step.text.strip():
        return None
    ref = result.hadith_ref
    if step.kind == "text_grounded" and step.from_hadith and ref is not None:
        return SmallStep(text=step.text.strip(), kind="text_grounded", grounded_in=[citation(ref)])
    kind = "reflection" if step.kind == "reflection" else "ethical_application"
    return SmallStep(text=step.text.strip(), kind=kind)


def build_insight(
    item: ComposedInsight,
    result: GateResult,
    scene: SceneAnalysis,
    learner: LearnerContext,
    path_version: str | None,
) -> ProposedInsight:
    """Assemble one insight from the composed text and the gate's decision."""
    quran = _reference(result.quran, result.quran_ref)
    hadith = _reference(result.hadith, result.hadith_ref)
    candidate = result.candidate
    life = item.life.strip()
    if candidate.content_level == "d":
        life = f"{life} {messages_for().engine_referral}".strip()
    unit = [unit_citation(candidate.unit.unit.unit_id)] if candidate.unit else []
    parts = [
        ExplanationPart(section="seen", text=item.seen.strip(), sources=unit),
        ExplanationPart(section="value", text=item.value.strip(), sources=unit),
    ]
    if quran is not None and item.quran:
        sources = [citation(quran.ref), *unit]
        parts.append(ExplanationPart(section="quran", text=item.quran.strip(), sources=sources))
    if hadith is not None and item.sunnah:
        sources = [citation(hadith.ref), *unit]
        parts.append(ExplanationPart(section="sunnah", text=item.sunnah.strip(), sources=sources))
    parts.append(ExplanationPart(section="life", text=life, sources=unit))
    boxes = {entity.id: entity.bbox for entity in scene.entities}
    anchor: BBox | None = next(
        (boxes[e] for e in candidate.entity_ids if boxes.get(e) is not None), None
    )
    chosen = [c for c in (result.quran, result.hadith) if c is not None]
    return ProposedInsight(
        title=item.title.strip() or candidate.title,
        glimpse=item.glimpse.strip() or candidate.glimpse,
        entity_ids=list(candidate.entity_ids),
        action_ids=list(candidate.action_ids),
        anchor=anchor,
        relation=result.relation,
        quran=quran,
        hadith=hadith,
        explanation=parts,
        why=WhyThis(
            visible_clues=list(candidate.visible_clues),
            concept=item.why_concept.strip() or candidate.concept,
            ontology_entity_ids=list(candidate.ontology_ids),
            limits=list(dict.fromkeys([*candidate.limits, *(c.limit for c in chosen if c.limit)])),
            personalised_because=personalised_reason(
                candidate.unit,
                learner,
                review=any(c.review for c in chosen),
                new_text=any(c.unseen_preferred for c in chosen),
            ),
        ),
        small_step=_step(item, result),
        learning_unit_id=candidate.unit.unit.unit_id if candidate.unit else None,
        learning_path_version=path_version if candidate.unit else None,
    )


class InsightComposer:
    """Writes the explanation of the insights that passed the gate."""

    def __init__(self, client: ModelClient, *, attempts: int = 2) -> None:
        self._client = client
        self._attempts = attempts

    async def compose(
        self,
        scene: SceneAnalysis,
        results: Sequence[GateResult],
        learner: LearnerContext,
        guard: EngineGuard,
        path_version: str | None,
    ) -> Composition:
        """
        Write every insight in a call of its own, all at once.

        No insight's text depends on another's, and one long answer took as long as
        several short ones side by side. The first error of any call is raised.
        """
        system = load_prompt(SYSTEM_PROMPT)
        written = await asyncio.gather(
            *(self._compose_one(system.text, scene, result, learner, guard) for result in results),
            return_exceptions=True,
        )
        for outcome in written:
            if isinstance(outcome, BaseException):
                raise outcome
        clean = {
            index: item for index, item in enumerate(written) if isinstance(item, ComposedInsight)
        }
        built = {
            index: build_insight(clean[index], result, scene, learner, path_version)
            for index, result in enumerate(results)
            if index in clean
        }
        # Refused before returning: a part or a step citing anything but its own texts.
        insights = [insight for insight in built.values() if cites_only_its_own(insight)]
        leaked = [index for index in range(len(results)) if index not in clean]
        return Composition(insights, leaked, system.version)

    async def _compose_one(
        self,
        system: str,
        scene: SceneAnalysis,
        result: GateResult,
        learner: LearnerContext,
        guard: EngineGuard,
    ) -> ComposedInsight | None:
        """Write one insight; an answer that leaks is asked again, then the insight is dropped."""
        user = composer_message(scene, [result], learner)
        for _ in range(self._attempts):
            output = await self._client.chat_json(
                ComposerOutput,
                stage=AiStage.COMPOSE,
                system=system,
                user=user,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            )
            for item in output.value.insights:
                if item.insight == 0 and not await guard.leaks(composer_texts(item).values()):
                    return item
        return None
