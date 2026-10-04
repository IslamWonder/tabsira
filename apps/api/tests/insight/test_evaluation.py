"""`make eval`: the engine evaluation, its report and its command, with fake models."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from src.ai.errors import AiCallError, AiErrorCode
from src.cli import evaluate as command
from src.config import AiProvider
from src.evaluation.engine_eval import (
    ENGINE_GOLD,
    EvaluationResult,
    SceneRun,
    hadith_texts,
    hoped_found,
    insight_texts,
    load_engine_gold,
    resolve_evidence,
    summary,
)
from src.evaluation.evaluation_report import render
from src.evaluation.gold import load_gold
from src.pipeline.engine import (
    EngineRequest,
    EngineResult,
    EngineStage,
    EngineStatus,
    EvidenceRef,
    ExplanationPart,
    HadithRef,
    ProposedInsight,
    QuranRef,
    RelationType,
    SmallStep,
    WhyThis,
)
from tests.fakes import FakeModelClient
from tests.scripture.fixtures import verse_text

SCENES = command.SCENES_DIR


def insight(
    quran: tuple[int, int] = (30, 50), hadith: tuple[str, str] | None = None, **fields: Any
) -> ProposedInsight:
    def ref(value: Any) -> EvidenceRef:
        return EvidenceRef(
            ref=value, relation=RelationType.DIRECT, retrieval_score=0.1, matched_on="q"
        )

    return ProposedInsight(
        **(
            {
                "title": "الحياة في قطرة",
                "glimpse": "لمحة",
                "entity_ids": ["e1"],
                "anchor": None,
                "relation": RelationType.DIRECT,
                "quran": ref(QuranRef(surah=quran[0], ayah=quran[1])),
                "hadith": ref(HadithRef(collection=hadith[0], number=hadith[1]))
                if hadith
                else None,
                "explanation": [ExplanationPart(section="value", text="شرح")],
                "why": WhyThis(
                    visible_clues=["قطرات"],
                    concept="إحياء",
                    limits=["حد"],
                    personalised_because="لأنك",
                ),
                "small_step": SmallStep(text="خطوة", kind="reflection"),
            }
            | fields
        )
    )


class FakeEngine:
    def __init__(self, result: EngineResult) -> None:
        self.result = result
        self.requests: list[EngineRequest] = []

    async def propose(self, request: EngineRequest, on_stage: Any = None) -> EngineResult:
        self.requests.append(request)
        return self.result


def scene_answer(description: str = "مطر خفيف يسقط على أرض متشققة.") -> dict[str, Any]:
    return {
        "description": description,
        "entities": [
            {
                "id": "e1",
                "label": "rain",
                "label_arabic": "مطر",
                "detector_id": None,
                "box": None,
                "status": "observed",
            }
        ],
        "actions": [],
        "relations": [],
        "ambiguities": [],
        "clarification_question": None,
        "sensitive": [],
    }


def factory_for(answers: list[Any], result: EngineResult) -> Any:
    def build(log: Any) -> tuple[FakeModelClient, FakeEngine]:
        return FakeModelClient(AiProvider.OVH, answers=list(answers), log=log), FakeEngine(result)

    return build


def test_the_engine_gold_names_every_gold_scene_once():
    gold = load_engine_gold()
    scenes = {scene.id for scene in load_gold(SCENES / "gold.json").scenes}

    assert sorted(item.scene for item in gold.scenes) == sorted(scenes)
    assert {item.expect for item in gold.scenes} == {"insight", "abstain"}
    assert ENGINE_GOLD.name == "engine-gold.json"


async def test_evidence_resolves_to_stored_hash_checked_texts(store):
    good = insight(hadith=("bukhari", "1032"))
    missing = insight(quran=(99, 1), hadith=("bukhari", "9999"))

    keys, broken = await resolve_evidence(store, good)
    _, gone = await resolve_evidence(store, missing)
    shown = await hadith_texts(store, [HadithRef(collection="bukhari", number="1032")])

    assert keys == ["Q:30:50", "H:bukhari:1032"]
    assert broken == []
    assert gone == ["Q:99:1", "H:bukhari:9999"]
    assert len(shown) == 1
    assert await hadith_texts(store, []) == []


def test_every_text_a_person_reads_is_checked_and_hoped_texts_match_ranges():
    texts = insight_texts(insight())

    assert {
        "title",
        "glimpse",
        "why.concept",
        "explanation.value",
        "why.limits.0",
        "small_step",
    } <= set(texts)
    assert "why.personalised_because" in texts
    assert "small_step" not in insight_texts(
        insight(small_step=None, why=WhyThis(visible_clues=[], concept="c"))
    )
    assert hoped_found(["Q:3:190-191", "Q:30:50"], ["Q:3:191", "H:bukhari:1"]) == ["Q:3:190-191"]


async def _prepared(names: list[str]) -> list[Any]:
    from src.evaluation.benchmark import prepare_scenes
    from src.pipeline.detector import DetectorClient

    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _r: httpx.Response(503)))
    detector = DetectorClient("http://vision", http, timeout_seconds=1)
    from src.config import Settings

    return await prepare_scenes(
        load_gold(SCENES / "gold.json"),
        SCENES,
        names,
        settings=Settings(_env_file=None),
        detector=detector,
    )


async def test_scenes_are_run_checked_and_stopped_at_the_spend_cap(store, monkeypatch):
    from src.evaluation import engine_eval
    from src.pipeline.insight.guard import quran_detector

    prepared = await _prepared(["rain", "emblem", "tree"])
    leaking = insight(title=f"قال تعالى: «{verse_text(30, 50)}»")
    ok = EngineResult(
        status=EngineStatus.OK,
        insights=[insight(), leaking],
        awaiting_ruling=[HadithRef(collection="bukhari", number="1032")],
        stage_ms={EngineStage.SEARCHING: 120},
    )

    result = await engine_eval.run_evaluation(
        store,
        prepared,
        load_engine_gold(),
        factory_for([scene_answer()], ok),
        await quran_detector(store),
        provider="ovh",
        models={"vision": "fake"},
        max_cost_usd=0.002,
    )

    (run,) = result.runs
    assert run.scene == "rain"
    assert run.correct
    assert run.leaks == ["insights.1.title"]
    assert run.evidence == ["Q:30:50", "Q:30:50"]
    assert run.hoped_found == ["Q:30:50"]
    assert run.stage_ms == {"searching": 120}
    assert run.cost_usd > 0
    assert result.detector_available == 0


async def test_a_vision_failure_or_a_vision_leak_is_a_failed_scene(store):
    from src.evaluation import engine_eval
    from src.pipeline.insight.guard import quran_detector

    prepared = await _prepared(["emblem", "phone-alone"])
    abstained = EngineResult(status=EngineStatus.NO_RELEVANT_EVIDENCE)
    failing = factory_for([AiCallError(AiErrorCode.TIMEOUT, "slow")], abstained)
    leaking = factory_for([scene_answer(f"«{verse_text(30, 50)}»")], abstained)
    seen: list[SceneRun] = []

    async def collect(run: SceneRun) -> None:
        seen.append(run)

    first = await engine_eval.run_evaluation(
        store, prepared[:1], load_engine_gold(), failing, await quran_detector(store),
        provider="ovh", models={}, on_scene=collect,
    )  # fmt: skip
    second = await engine_eval.run_evaluation(
        store, prepared[1:], load_engine_gold(), leaking, await quran_detector(store),
        provider="ovh", models={},
    )  # fmt: skip

    assert first.runs[0].status == "vision_failed"
    assert second.runs[0].status == "vision_leak"
    assert not first.runs[0].correct
    assert seen == first.runs


def _evaluation() -> EvaluationResult:
    from datetime import UTC, datetime

    def run(scene: str, expected: str, status: str, correct: bool, **fields: Any) -> SceneRun:
        return SceneRun(
            **(
                {
                    "scene": scene,
                    "expected": expected,
                    "status": status,
                    "correct": correct,
                    "insights": 1,
                    "relations": ["direct"],
                    "evidence": ["Q:30:50"],
                    "unresolved": [],
                    "leaks": [],
                    "hoped": ["Q:30:50"],
                    "hoped_found": ["Q:30:50"],
                    "awaiting_ruling": 1,
                    "clarification_question": None,
                    "vision_ms": 4000,
                    "stage_ms": {"understanding": 3000},
                    "total_ms": 20000,
                    "cost_usd": 0.02,
                    "calls": 5,
                }
                | fields
            )
        )

    return EvaluationResult(
        started_at=datetime(2026, 10, 4, tzinfo=UTC),
        finished_at=datetime(2026, 10, 4, tzinfo=UTC),
        provider="openai",
        models={"vision": "m"},
        detector_available=0,
        runs=[
            run("rain", "insight", "ok", True),
            run(
                "emblem",
                "abstain",
                "no_relevant_evidence",
                True,
                evidence=[],
                relations=[],
                insights=0,
            ),
            run("tv", "insight", "vision_failed", False, evidence=[], relations=[], stage_ms={}),
        ],
    )


def test_the_summary_and_the_report_state_every_measure():
    result = _evaluation()

    facts = summary(result)
    markdown = render(result, "results.json")
    empty = summary(result.model_copy(update={"runs": []}))

    assert (facts.scenes, facts.correct, facts.leaks) == (3, 2, 0)
    assert (facts.abstain_expected, facts.abstain_correct) == (1, 1)
    assert (facts.insight_expected, facts.insight_correct) == (2, 1)
    assert facts.relations == {"direct": 1}
    assert facts.stages["understanding"] == (3000.0, 3000.0)
    assert facts.cost_per_scan == pytest.approx(0.02)
    assert "| Scripture leakage (texts refused by the guard) | 0 |" in markdown
    assert "`no_relevant_evidence` 1" in markdown
    assert empty.cost_per_scan == 0.0
    assert empty.stages["whole scan"] == (0.0, 0.0)
    assert "none" in render(result.model_copy(update={"runs": []}), "r.json")


async def test_the_command_writes_results_and_report_and_fails_on_a_leak(maker, tmp_path, capsys):
    ok = EngineResult(status=EngineStatus.OK, insights=[insight()])
    leaking = EngineResult(
        status=EngineStatus.OK, insights=[insight(title=f"«{verse_text(30, 50)}»")]
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _r: httpx.Response(503)))
    arguments = [
        "--scenes", "rain",
        "--results-dir", str(tmp_path / "results"),
        "--report", str(tmp_path / "EVALUATION.md"),
    ]  # fmt: skip

    clean = await command.run(
        arguments, sessionmaker=maker, factory=factory_for([scene_answer()], ok), http=http
    )
    dirty = await command.run(
        [*arguments, "--no-report"],
        sessionmaker=maker,
        factory=factory_for([scene_answer()], leaking),
        http=httpx.AsyncClient(transport=httpx.MockTransport(lambda _r: httpx.Response(503))),
    )

    assert (clean, dirty) == (0, 1)
    assert "# Evaluation: the insight engine" in (tmp_path / "EVALUATION.md").read_text()
    saved = json.loads(next((tmp_path / "results").glob("evaluation-*.json")).read_text())
    assert saved["runs"][0]["scene"] == "rain"
    out = capsys.readouterr().out
    assert "rain: ok, 1 insights" in out
    assert "1 leaks" in out


async def test_the_command_builds_the_real_engine_and_closes_its_own(
    monkeypatch, make_settings, maker
):
    built: list[Any] = []

    def fake_build(settings, http, maker, *, log, resources):
        built.append(resources)
        return FakeEngine(EngineResult(status=EngineStatus.NO_RELEVANT_EVIDENCE))

    monkeypatch.setattr(command, "build_engine", fake_build)
    settings = make_settings(ai_provider="ovh")
    http = httpx.AsyncClient()
    factory = command.factory_for(settings, http, maker)

    client, engine = factory(None)
    _, again = factory(None)

    assert client.provider is AiProvider.OVH
    assert built[0] is built[1]

    disposed: list[bool] = []

    async def dispose() -> None:
        disposed.append(True)

    async def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("stop")

    monkeypatch.setattr(command, "dispose_engine", dispose)
    monkeypatch.setattr(command, "prepare_scenes", boom)
    with pytest.raises(RuntimeError):
        await command.run(["--no-report"], settings=settings)
    assert disposed == [True]
    assert engine is not again


def test_main_runs_the_command(monkeypatch):
    async def fake(argv):
        return 5

    monkeypatch.setattr(command, "run", fake)

    assert command.main([]) == 5
    assert command._relative(SCENES / "gold.json").endswith("gold.json")
    assert command._relative(__import__("pathlib").Path("/x/y")) == "/x/y"


async def test_a_clarification_question_that_quotes_scripture_counts_as_a_leak(store):
    from src.evaluation.engine_eval import check_result
    from src.pipeline.insight.guard import quran_detector

    expectation = load_engine_gold().scenes[0]
    asked = EngineResult(
        status=EngineStatus.NEEDS_CLARIFICATION,
        clarification_question=f"«{verse_text(30, 50)}»؟",
    )

    checked = await check_result(store, expectation, asked, await quran_detector(store))

    assert checked["leaks"] == ["clarification_question"]
    assert checked["correct"] is True
