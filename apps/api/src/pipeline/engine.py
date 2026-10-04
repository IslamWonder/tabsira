"""
The contract between the scan workflow and the insight engine.

The scan workflow (routes, queue, progress, saving) calls an `InsightEngine`
with the analysed scene and what the learner chose to share; the engine plans
candidate insights, retrieves and reranks evidence, applies the evidence gate
and writes the explanation. The engine returns evidence by reference only:
scripture text is never part of its output, the read API supplies it from the
store by id (AGENTS.md, decision 16 to 18).

Both sides are built against this module; neither redefines these shapes.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Annotated, Literal, Protocol

from pydantic import Field

from src.pipeline.schemas import BBox, FrozenModel, SceneAnalysis


class RelationType(StrEnum):
    """How an insight relates to the scene, strongest first (v2 §8)."""

    DIRECT = "direct"
    ACTION_BASED = "action_based"
    CLOSE_CONCEPTUAL = "close_conceptual"
    OPPOSITE = "opposite"
    THEMATIC_REMINDER = "thematic_reminder"


class EngineStage(StrEnum):
    """Honest progress stages the workflow shows while the engine works."""

    UNDERSTANDING = "understanding"  # «أفهم المشهد»
    SEARCHING = "searching"  # «أبحث عن الأدلة»
    VERIFYING = "verifying"  # «أتحقق من المصادر»
    COMPOSING = "composing"  # «أعدّ بصيرتك»


class EngineStatus(StrEnum):
    OK = "ok"
    NO_RELEVANT_EVIDENCE = "no_relevant_evidence"
    NEEDS_CLARIFICATION = "needs_clarification"
    SOURCE_UNAVAILABLE = "source_unavailable"
    MODEL_UNAVAILABLE = "model_unavailable"


class QuranRef(FrozenModel):
    kind: Literal["quran"] = "quran"
    surah: Annotated[int, Field(ge=1, le=114)]
    ayah: Annotated[int, Field(ge=1, le=286)]


class HadithRef(FrozenModel):
    kind: Literal["hadith"] = "hadith"
    collection: str
    number: str


class EvidenceRef(FrozenModel):
    """One piece of evidence, by reference, with why it was chosen."""

    ref: Annotated[QuranRef | HadithRef, Field(discriminator="kind")]
    relation: RelationType
    retrieval_score: float
    rerank_score: float | None = None
    # The concept or query the evidence answered, for «لماذا ظهر هذا؟».
    matched_on: str


class ExplanationPart(FrozenModel):
    """One labelled unit of the platform's own explanation («شرح تبصرة»)."""

    section: Literal["seen", "value", "quran", "sunnah", "life"]
    text: str
    # Supporting passages (masar units, curated notes) the text relies on.
    sources: list[str] = Field(default_factory=list)


class SmallStep(FrozenModel):
    text: str
    kind: Literal["text_grounded", "ethical_application", "reflection"]
    # Evidence ids that ground a step presented as «من السنة»; empty means «اقتراح عملي».
    grounded_in: list[str] = Field(default_factory=list)


class WhyThis(FrozenModel):
    """What «لماذا ظهر هذا؟» discloses: clue, concept, sources, limits, personalisation."""

    visible_clues: list[str]
    concept: str
    ontology_entity_ids: list[str] = Field(default_factory=list)
    limits: list[str] = Field(default_factory=list)
    personalised_because: str | None = None


class ProposedInsight(FrozenModel):
    title: str
    glimpse: str
    entity_ids: list[str]
    action_ids: list[str] = Field(default_factory=list)
    anchor: BBox | None
    relation: RelationType
    quran: EvidenceRef | None
    hadith: EvidenceRef | None
    explanation: list[ExplanationPart]
    why: WhyThis
    small_step: SmallStep | None = None
    learning_unit_id: str | None = None
    learning_path_version: str | None = None


class LearnerContext(FrozenModel):
    """What the learner shared and saw; never sent to the scene stage (decision 5)."""

    goals: list[str] = Field(default_factory=list)
    knowledge_level: str = "unknown"
    age_range: str = "unknown"
    religious_background: str = "unknown"
    personalization_enabled: bool = True
    seen_quran: list[QuranRef] = Field(default_factory=list)
    seen_hadith: list[HadithRef] = Field(default_factory=list)
    completed_units: list[str] = Field(default_factory=list)


class EngineRequest(FrozenModel):
    scan_id: str
    scene: SceneAnalysis
    focus_entity_id: str | None = None
    clarification_answer: str | None = None
    learner: LearnerContext = Field(default_factory=LearnerContext)
    max_insights: Annotated[int, Field(ge=1, le=3)] = 3


class EngineResult(FrozenModel):
    status: EngineStatus
    insights: list[ProposedInsight] = Field(default_factory=list)
    clarification_question: str | None = None
    # Hadith the engine wanted but that have no editor ruling yet (decision 18).
    awaiting_ruling: list[HadithRef] = Field(default_factory=list)
    stage_ms: dict[EngineStage, int] = Field(default_factory=dict)


ProgressCallback = Callable[[EngineStage], Awaitable[None]]


class InsightEngine(Protocol):
    async def propose(  # pragma: no cover - a protocol declares the call; implementations are tested
        self, request: EngineRequest, on_stage: ProgressCallback | None = None
    ) -> EngineResult: ...
