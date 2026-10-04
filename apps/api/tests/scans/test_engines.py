"""The engine injection point, the honest placeholder and the declared simulation."""

from __future__ import annotations

from src.config import ScanEngine
from src.pipeline.engine import EngineRequest, EngineStage, EngineStatus, RelationType
from src.scans import engines
from src.scans.engines import DemoEngine, UnavailableEngine
from tests.scans.builders import entity, scene


async def test_without_a_wired_engine_a_scan_says_the_model_side_is_unavailable():
    result = await UnavailableEngine().propose(EngineRequest(scan_id="s", scene=scene()))

    assert result.status is EngineStatus.MODEL_UNAVAILABLE
    assert result.insights == []


def test_the_setting_chooses_the_factory(make_settings):
    assert engines.engine_factory(make_settings()) is engines.unavailable_engine
    assert engines.engine_factory(make_settings(scan_engine="demo")) is engines.demo_engine
    assert set(engines.ENGINE_FACTORIES) == set(ScanEngine)
    assert isinstance(engines.unavailable_engine(None), UnavailableEngine)  # type: ignore[arg-type]
    assert isinstance(engines.demo_engine(None), DemoEngine)  # type: ignore[arg-type]


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
