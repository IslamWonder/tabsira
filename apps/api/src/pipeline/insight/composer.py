"""
The composer: the platform's own explanation of each insight («شرح تبصرة»), never the texts.

A chat model (structured output) writes the title, the five parts of v2 §12
(what appeared, the value, what the verse adds, what the hadith adds, life),
the concept of «لماذا ظهر هذا؟» and one small optional step, in Arabic
adapted to the learner's declared level. It writes after the evidence: it
receives the confirmed intent, the shared meaning, the verifier's link of
each text and the limits, and the meaning of the chosen texts as folded
Arabic so it can explain them. It cites them by reference only: every field
goes through the leak guard, whose corpus includes those texts, and an answer
that leaks is asked again within the stage's bound; an insight whose text
still leaks is dropped.

The server, not the model, decides what is shown: a part about a verse or a
hadith exists only when that text was chosen; a step is «من السنة» only when
the chosen hadith grounds it, otherwise it is a practical suggestion; a
personal matter (content level «د») ends with the referral to a qualified
scholar (v2 §12, rule 7). The learner's profile reaches this stage only, for
the level and the wording (the brief of 2026-10-05, §14).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

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
    SmallStep,
    WhyThis,
)
from src.pipeline.insight.evidence import TEXT_CHARS, Chosen, GateResult
from src.pipeline.insight.guard import EngineGuard
from src.pipeline.insight.learning import UnitOption, personalised_reason
from src.pipeline.prompt import load_prompt
from src.pipeline.schemas import BBox, SceneAnalysis

SYSTEM_PROMPT = "insight_composer_system.v4"
# A part's sources name the insight's own texts (quran:S:A, hadith:C:N) or its unit.
UNIT_PREFIX = "masar:"
MAX_OUTPUT_TOKENS = 2000

# The one background the composer may write for as a believer; every other value, and an
# absent one, gets the neutral «يعلّم الإسلام» framing (v2 §5). The prompt names these.
BACKGROUND_MUSLIM = "muslim"
BACKGROUND_NON_MUSLIM = "non_muslim"
BACKGROUND_UNKNOWN = "unknown"


class ComposedStep(BaseModel):
    text: str
    kind: Literal["text_grounded", "ethical_application", "reflection"]
    from_hadith: bool


class ComposedInsight(BaseModel):
    title: str
    glimpse: str
    seen: str
    value: str
    quran: str | None
    sunnah: str | None
    life: str
    why_concept: str
    small_step: ComposedStep | None


@dataclass(frozen=True, slots=True)
class Composable:
    """One gate result with what the server settled around it: its unit and its clues."""

    result: GateResult
    unit: UnitOption | None
    # The scene's own words for the clues the intent rests on (labels of its anchors).
    visible_clues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Composition:
    insights: list[ProposedInsight]
    # Indexes of gate results whose text kept leaking and were dropped.
    leaked: list[int]
    prompt_version: str


def learner_payload(learner: LearnerContext) -> dict[str, Any]:
    """
    Return what the learner shared, without its history and its `unknown` fields.

    The religious background stays as the profile enum writes it (`muslim`, `non_muslim`)
    and is left out when unknown, so the composer prompt's rule, which is keyed on these very
    values, fires for a non-Muslim and for a background that was never shared alike.
    """
    shared = {
        "knowledge_level": learner.knowledge_level,
        "age_range": learner.age_range,
        "religious_background": learner.religious_background,
    }
    payload: dict[str, Any] = {
        key: value for key, value in shared.items() if value != BACKGROUND_UNKNOWN
    }
    if learner.goals:
        payload["goals"] = list(learner.goals)
    return payload


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


def limits_of(result: GateResult) -> list[str]:
    """Return the limits of the inference: the intent's, then what the texts' links need."""
    intent = result.intent
    limits = [*intent.uncertainties, *intent.unsupported_assumptions]
    for chosen in (result.quran, result.hadith):
        if chosen is None:
            continue
        limits += list(chosen.assumptions)
        if chosen.needed_context:
            limits.append(chosen.needed_context)
    return list(dict.fromkeys(limit for limit in limits if limit))


def _text_view(chosen: Chosen | None) -> dict[str, Any] | None:
    if chosen is None:
        return None
    return {
        "meaning": chosen.found.document.text[:TEXT_CHARS],
        "relation": chosen.relation.value,
        "link": chosen.link,
    }


def composer_message(scene: SceneAnalysis, item: Composable, learner: LearnerContext) -> str:
    learner_view = learner_payload(learner) if learner.personalization_enabled else {}
    result = item.result
    intent = result.intent
    payload: dict[str, Any] = {
        "scene": scene.description,
        "learner": {"level": learner_view.get("knowledge_level", "beginner"), **learner_view},
        "insight": {
            "intent": {
                "observable_meaning": intent.observable_meaning,
                "relation_description": intent.relation_description,
                "candidate_concept": intent.candidate_concept,
                "concept_basis": intent.concept_basis,
            },
            "relation": result.relation.value,
            "shared_meaning": result.shared_meaning,
            "content_level": intent.content_level,
            "visible_clues": list(item.visible_clues),
            "limits": limits_of(result),
            "verse": _text_view(result.quran),
            "hadith": _text_view(result.hadith),
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def _reference(chosen: Chosen | None, ref: QuranRef | HadithRef | None) -> EvidenceRef | None:
    if chosen is None or ref is None:
        return None
    return EvidenceRef(
        ref=ref,
        relation=chosen.relation,
        retrieval_score=round(chosen.found.retrieval_score, 6),
        rerank_score=chosen.found.rerank_score,
        matched_on=chosen.found.matched_on,
        link=chosen.link or None,
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
    composable: Composable,
    scene: SceneAnalysis,
    learner: LearnerContext,
    path_version: str | None,
) -> ProposedInsight:
    """Assemble one insight from the composed text and the gate's decision."""
    result, unit_option = composable.result, composable.unit
    quran = _reference(result.quran, result.quran_ref)
    hadith = _reference(result.hadith, result.hadith_ref)
    intent = result.intent
    life = item.life.strip()
    if intent.content_level == "d":
        life = f"{life} {messages_for().engine_referral}".strip()
    unit = [unit_citation(unit_option.unit.unit_id)] if unit_option else []
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
        (boxes[e] for e in intent.entity_ids if boxes.get(e) is not None), None
    )
    chosen = [c for c in (result.quran, result.hadith) if c is not None]
    return ProposedInsight(
        title=item.title.strip() or intent.candidate_concept,
        glimpse=item.glimpse.strip() or intent.observable_meaning,
        entity_ids=list(intent.entity_ids),
        action_ids=list(intent.action_ids),
        anchor=anchor,
        relation=result.relation,
        quran=quran,
        hadith=hadith,
        explanation=parts,
        why=WhyThis(
            visible_clues=list(composable.visible_clues),
            concept=item.why_concept.strip() or intent.candidate_concept,
            ontology_entity_ids=list(intent.ontology_ids),
            limits=limits_of(result),
            personalised_because=personalised_reason(
                unit_option,
                learner,
                review=any(c.review for c in chosen),
                new_text=any(c.unseen_preferred for c in chosen),
            ),
        ),
        small_step=_step(item, result),
        learning_unit_id=unit_option.unit.unit_id if unit_option else None,
        learning_path_version=path_version if unit_option else None,
    )


class InsightComposer:
    """Writes the explanation of the insights that passed the gate."""

    def __init__(self, client: ModelClient, *, attempts: int = 2) -> None:
        self._client = client
        self._attempts = attempts

    async def compose(
        self,
        scene: SceneAnalysis,
        items: Sequence[Composable],
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
            *(self._compose_one(system.text, scene, item, learner, guard) for item in items),
            return_exceptions=True,
        )
        for outcome in written:
            if isinstance(outcome, BaseException):
                raise outcome
        clean = {
            index: item for index, item in enumerate(written) if isinstance(item, ComposedInsight)
        }
        built = {
            index: build_insight(clean[index], composable, scene, learner, path_version)
            for index, composable in enumerate(items)
            if index in clean
        }
        # Refused before returning: a part or a step citing anything but its own texts.
        insights = [insight for insight in built.values() if cites_only_its_own(insight)]
        leaked = [index for index in range(len(items)) if index not in clean]
        return Composition(insights, leaked, system.version)

    async def _compose_one(
        self,
        system: str,
        scene: SceneAnalysis,
        item: Composable,
        learner: LearnerContext,
        guard: EngineGuard,
    ) -> ComposedInsight | None:
        """Write one insight; an answer that leaks is asked again, then the insight is dropped."""
        user = composer_message(scene, item, learner)
        for _ in range(self._attempts):
            output = await self._client.chat_json(
                ComposedInsight,
                stage=AiStage.COMPOSE,
                system=system,
                user=user,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            )
            if not await guard.leaks(composer_texts(output.value).values()):
                return output.value
        return None
