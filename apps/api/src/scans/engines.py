"""
Which insight engine a scan runs, and the one place where the engines are plugged in.

The scan workflow calls `InsightEngine.propose` (src/pipeline/engine.py) and
nothing else of the engine. `ENGINE_FACTORIES` maps SCAN_ENGINE to a factory
that builds an engine from `EngineDeps`; the job builds one engine per run.

- `pipeline`: the real engine of src/pipeline/insight (`build_engine`), built
  with the scan's own client so every model call it makes is recorded with
  the scan's. A provider that fails ends the scan with MODEL_UNAVAILABLE, never
  with an invented result.
- `demo`: `DemoEngine`, a declared simulation for development and smoke
  tests (production refuses it). It never calls a model; it cites one verse
  the store holds, as a general reminder, and every insight it makes says so.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.ai.client import ModelClient
from src.config import ScanEngine, Settings
from src.pipeline.engine import (
    EngineRequest,
    EngineResult,
    EngineStage,
    EngineStatus,
    EvidenceRef,
    ExplanationPart,
    InsightEngine,
    ProgressCallback,
    ProposedInsight,
    QuranRef,
    RelationType,
    SmallStep,
    WhyThis,
)
from src.pipeline.insight.engine import build_engine


@dataclass(frozen=True)
class EngineDeps:
    """What an engine may use: the settings, the provider client of the run, the database, HTTP."""

    settings: Settings
    client: ModelClient
    sessionmaker: async_sessionmaker[AsyncSession]
    http: httpx.AsyncClient


EngineFactory = Callable[[EngineDeps], InsightEngine]


# The reminder the simulation cites: Al Imran 3:190, the first verse of unit T01_01.
DEMO_VERSE = QuranRef(surah=3, ayah=190)
DEMO_UNIT = "T01_01"
DEMO_PATH_VERSION = "tabsira-masar-1.0"


class DemoEngine:
    """
    A declared simulation of the engine, for development and smoke tests only.

    It reports the three stages, asks the scene's own question once when there
    is one, finds nothing when the scene names nothing, and otherwise proposes
    one general reminder anchored on the first thing seen. Its texts say it is
    a simulation; the verse is cited by reference and read from the store.
    """

    async def propose(
        self, request: EngineRequest, on_stage: ProgressCallback | None = None
    ) -> EngineResult:
        for stage in (EngineStage.SEARCHING, EngineStage.VERIFYING, EngineStage.COMPOSING):
            if on_stage is not None:
                await on_stage(stage)
        scene = request.scene
        if scene.clarification_question and request.clarification_answer is None:
            return EngineResult(
                status=EngineStatus.NEEDS_CLARIFICATION,
                clarification_question=scene.clarification_question,
            )
        focus = next(
            (entity for entity in scene.entities if entity.id == request.focus_entity_id),
            scene.entities[0] if scene.entities else None,
        )
        if focus is None:
            return EngineResult(status=EngineStatus.NO_RELEVANT_EVIDENCE)
        insight = ProposedInsight(
            title="تأمّل ما تراه",
            glimpse="محاكاة للتطوير: تذكير عام بالتفكر في الخلق.",
            entity_ids=[focus.id],
            anchor=focus.bbox,
            relation=RelationType.THEMATIC_REMINDER,
            quran=EvidenceRef(
                ref=DEMO_VERSE,
                relation=RelationType.THEMATIC_REMINDER,
                retrieval_score=0.0,
                matched_on="التفكر في الخلق",
            ),
            hadith=None,
            explanation=[
                ExplanationPart(section="seen", text=f"يظهر في الصورة: {focus.label_arabic}."),
                ExplanationPart(
                    section="value",
                    text="هذه محاكاة للتطوير، لا تحليل حي: تذكير عام بالتفكر في ما خلق الله.",
                ),
            ],
            why=WhyThis(
                visible_clues=[focus.label_arabic],
                concept="التفكر",
                limits=["محاكاة معلنة؛ لا تُبنى عليها صلة بالمشهد."],
            ),
            small_step=SmallStep(
                text="تأمّل دقيقة في شيء واحد حولك.", kind="reflection", grounded_in=[]
            ),
            learning_unit_id=DEMO_UNIT,
            learning_path_version=DEMO_PATH_VERSION,
        )
        return EngineResult(status=EngineStatus.OK, insights=[insight])


def pipeline_engine(deps: EngineDeps) -> InsightEngine:
    """Build the src/pipeline engine for one scan, on the scan's client, database and HTTP."""
    return build_engine(deps.settings, deps.http, deps.sessionmaker, client=deps.client)


def demo_engine(_deps: EngineDeps) -> InsightEngine:
    return DemoEngine()


ENGINE_FACTORIES: dict[ScanEngine, EngineFactory] = {
    ScanEngine.PIPELINE: pipeline_engine,
    ScanEngine.DEMO: demo_engine,
}


def engine_factory(settings: Settings) -> EngineFactory:
    """Return the factory of the engine SCAN_ENGINE names."""
    return ENGINE_FACTORIES[settings.scan_engine]
