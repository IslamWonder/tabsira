"""The engine injection point: the real engine and the declared simulation."""

from __future__ import annotations

import httpx

from src.config import ScanEngine
from src.pipeline.engine import EngineRequest, EngineStage, EngineStatus, RelationType
from src.pipeline.insight.engine import PipelineInsightEngine
from src.scans import engines
from src.scans.engines import DemoEngine, EngineDeps
from tests.fakes import FakeModelClient
from tests.scans.builders import entity, scene


def test_the_setting_chooses_the_factory(make_settings):
    assert engines.engine_factory(make_settings()) is engines.pipeline_engine
    assert engines.engine_factory(make_settings(scan_engine="demo")) is engines.demo_engine
    assert set(engines.ENGINE_FACTORIES) == set(ScanEngine)
    assert isinstance(engines.demo_engine(None), DemoEngine)  # type: ignore[arg-type]


async def test_the_pipeline_engine_runs_on_the_scan_s_own_client(make_settings):
    client = FakeModelClient()
    async with httpx.AsyncClient() as http:
        deps = EngineDeps(
            settings=make_settings(),
            client=client,
            sessionmaker=None,  # type: ignore[arg-type]
            http=http,
        )

        engine = engines.pipeline_engine(deps)

    assert isinstance(engine, PipelineInsightEngine)
    # Every call the engine makes is recorded with the scan's calls.
    assert engine._client is client


async def test_the_simulation_reports_its_stages_and_cites_a_stored_reference():
    stages: list[EngineStage] = []

    async def on_stage(stage: EngineStage) -> None:
        stages.append(stage)

    request = EngineRequest(
        scan_id="s",
        scene=scene(entity("e1", "نبتة"), entity("e2", "قطرة")),
        focus_entity_id="e2",
    )
    result = await DemoEngine().propose(request, on_stage)

    assert stages == [EngineStage.SEARCHING, EngineStage.VERIFYING, EngineStage.COMPOSING]
    assert result.status is EngineStatus.OK
    insight = result.insights[0]
    assert insight.entity_ids == ["e2"]
    assert insight.relation is RelationType.THEMATIC_REMINDER
    assert insight.quran is not None
    assert insight.quran.ref == engines.DEMO_VERSE
    assert insight.hadith is None
    assert "محاكاة" in insight.glimpse


async def test_the_simulation_asks_the_scene_question_once_and_finds_nothing_in_an_empty_scene():
    asking = scene(clarification_question="ما الذي يحدث هنا؟")

    first = await DemoEngine().propose(EngineRequest(scan_id="s", scene=asking))
    answered = await DemoEngine().propose(
        EngineRequest(scan_id="s", scene=asking, clarification_answer="مطر")
    )
    empty = await DemoEngine().propose(EngineRequest(scan_id="s", scene=scene(entities=[])))

    assert first.status is EngineStatus.NEEDS_CLARIFICATION
    assert first.clarification_question == "ما الذي يحدث هنا؟"
    assert answered.status is EngineStatus.OK
    assert answered.insights[0].entity_ids == ["e1"]
    assert empty.status is EngineStatus.NO_RELEVANT_EVIDENCE
