"""The insight engine end to end, on the fixture store, with fake models."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from src.ai.errors import AiCallError, AiErrorCode
from src.config import AiProvider
from src.models import Hadith, HadithClassification, HadithVerificationQueue
from src.pipeline.engine import (
    EngineRequest,
    EngineStage,
    EngineStatus,
    HadithRef,
    LearnerContext,
    QuranRef,
    RelationType,
)
from src.pipeline.insight import engine as engine_module
from src.pipeline.insight.engine import PipelineInsightEngine, ResourceCache, build_engine
from src.pipeline.insight.search import Embedding
from src.retrieval.reranker import LlmReranker, RerankerClient
from src.scripture.rulings import RulingInput, record_ruling
from tests.fakes import FakeModelClient
from tests.insight.support import (
    compose_answer,
    composed,
    entity,
    plan_answer,
    planned,
    rain_scene,
    scene,
    verdict,
    verify_answer,
)
from tests.retrieval.support import EmbeddingClient
from tests.scripture.fixtures import verse_text


def _labels(call: dict[str, Any], candidate: int = 0) -> list[str]:
    payload = json.loads(call["user"])
    return [text["label"] for text in payload["candidates"][candidate]["texts"]]


def verify_all(strength: str = "strong", relation: str = "direct") -> Any:
    """A verifier that finds every shortlisted text relevant."""

    def answer(call: dict[str, Any]) -> dict[str, Any]:
        payload = json.loads(call["user"])
        return {
            "candidates": [
                {
                    "candidate": item["candidate"],
                    "texts": [
                        verdict(text["label"], strength=strength, relation=relation)
                        for text in item["texts"]
                    ],
                }
                for item in payload["candidates"]
            ]
        }

    return answer


def verify_none(call: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(call["user"])
    return {
        "candidates": [
            {
                "candidate": item["candidate"],
                "texts": [verdict(t["label"], relevant=False) for t in item["texts"]],
            }
            for item in payload["candidates"]
        ]
    }


def make_engine(
    maker, answers, *, reranker=None, embedding=True, rounds=2
) -> tuple[PipelineInsightEngine, EmbeddingClient]:
    client = EmbeddingClient()
    client.answers = list(answers)
    engine = PipelineInsightEngine(
        maker,
        client,
        embedding=Embedding(client, "fake-embed", 8) if embedding else None,
        reranker=reranker,
        refinement_rounds=rounds,
        resources=ResourceCache(),
    )
    return engine, client


async def test_a_rain_scene_gets_an_insight_backed_by_its_verse_while_the_hadith_waits(maker):
    engine, client = make_engine(
        maker,
        [plan_answer(planned()), verify_all(), compose_answer(composed())],
    )
    stages: list[EngineStage] = []

    async def on_stage(stage: EngineStage) -> None:
        stages.append(stage)

    result = await engine.propose(EngineRequest(scan_id="s1", scene=rain_scene()), on_stage)

    assert result.status is EngineStatus.OK
    assert stages == [
        EngineStage.UNDERSTANDING,
        EngineStage.SEARCHING,
        EngineStage.VERIFYING,
        EngineStage.COMPOSING,
    ]
    assert set(result.stage_ms) == set(stages)
    (insight,) = result.insights
    assert isinstance(insight.quran.ref, QuranRef)
    # No hadith has an editor's ruling: the insight carries its verse alone.
    assert insight.hadith is None
    assert [part.section for part in insight.explanation] == ["seen", "value", "quran", "life"]
    assert insight.explanation[0].sources == ["masar:T01_06"]
    assert insight.explanation[2].sources == [
        f"quran:{insight.quran.ref.surah}:{insight.quran.ref.ayah}",
        "masar:T01_06",
    ]
    assert insight.small_step.kind == "ethical_application"
    assert insight.learning_unit_id == "T01_06"
    assert insight.learning_path_version == "tabsira-masar-1.0"
    assert insight.anchor is not None
    assert insight.why.personalised_because is not None
    assert result.awaiting_ruling
    async with maker() as session:
        queued = await session.scalar(select(HadithVerificationQueue.demand_count))
    assert queued == 1
    assert [call["stage"].value for call in client.calls] == ["planner", "verify", "compose"]


async def test_an_eligible_hadith_completes_the_pair_and_grounds_the_step(maker):
    async with maker() as session, session.begin():
        for hadith_id in await session.scalars(select(Hadith.id)):
            await record_ruling(
                session,
                hadith_id,
                RulingInput(
                    ruling_text="صحيح",
                    scholar="محرر",
                    source_book="كتاب",
                    page="1",
                    dorar_url="https://dorar.net/hadith/sharh/1",
                    classification=HadithClassification.SAHIH,
                    editor_name="محرر",
                ),
            )
    engine, _ = make_engine(
        maker, [plan_answer(planned()), verify_all(), compose_answer(composed())]
    )

    result = await engine.propose(EngineRequest(scan_id="s2", scene=rain_scene()))

    (insight,) = result.insights
    assert isinstance(insight.hadith.ref, HadithRef)
    assert insight.small_step.kind == "text_grounded"
    assert insight.small_step.grounded_in == [
        f"hadith:{insight.hadith.ref.collection}:{insight.hadith.ref.number}"
    ]
    assert [part.section for part in insight.explanation][2:4] == ["quran", "sunnah"]
    assert result.awaiting_ruling == []


async def test_a_text_already_seen_is_shown_again_as_a_review_when_none_is_as_strong(maker):
    engine, client = make_engine(
        maker, [plan_answer(planned()), verify_all(), compose_answer(composed())]
    )
    first = await engine.propose(EngineRequest(scan_id="s3", scene=rain_scene()))
    seen = first.insights[0].quran.ref

    def only_first(call: dict[str, Any]) -> dict[str, Any]:
        return verify_answer([verdict("Q1")])

    client.answers = [plan_answer(planned()), only_first, compose_answer(composed())]
    again = await engine.propose(
        EngineRequest(
            scan_id="s4",
            scene=rain_scene(),
            learner=LearnerContext(seen_quran=[seen], completed_units=["T00_01"]),
        )
    )

    assert again.insights[0].quran.ref == seen
    assert "مراجعة" in (again.insights[0].why.personalised_because or "")


async def test_a_scan_focused_on_a_blocked_entity_stops(maker):
    engine, client = make_engine(maker, [])
    hand = scene([entity("e1", "hand", "يد")])

    result = await engine.propose(EngineRequest(scan_id="s5", scene=hand, focus_entity_id="e1"))

    assert result.status is EngineStatus.NO_RELEVANT_EVIDENCE
    assert client.calls == []


async def test_a_scan_focused_on_an_unclear_entity_asks_its_question_first(maker):
    engine, _ = make_engine(maker, [])
    unclear = scene([entity("e1", "zzqq", "شيء غامض جدا")])

    result = await engine.propose(EngineRequest(scan_id="s6", scene=unclear, focus_entity_id="e1"))

    assert result.status is EngineStatus.NEEDS_CLARIFICATION
    assert result.clarification_question


async def test_no_plan_asks_the_planner_question_or_the_scene_question_or_abstains(maker):
    engine, client = make_engine(
        maker, [plan_answer(needs_clarification=True, clarification_question="ماذا يحدث هنا؟")]
    )
    asked = await engine.propose(EngineRequest(scan_id="s7", scene=rain_scene()))
    client.answers = [plan_answer()]
    from_scene = await engine.propose(
        EngineRequest(scan_id="s8", scene=rain_scene(question="لمن هذا الهاتف؟"))
    )
    client.answers = [plan_answer()]
    abstained = await engine.propose(EngineRequest(scan_id="s9", scene=rain_scene()))
    client.answers = [plan_answer()]
    answered = await engine.propose(
        EngineRequest(
            scan_id="s10", scene=rain_scene(question="لمن هذا؟"), clarification_answer="لي"
        )
    )

    assert (asked.status, asked.clarification_question) == (
        EngineStatus.NEEDS_CLARIFICATION,
        "ماذا يحدث هنا؟",
    )
    assert from_scene.clarification_question == "لمن هذا الهاتف؟"
    assert abstained.status is EngineStatus.NO_RELEVANT_EVIDENCE
    assert answered.status is EngineStatus.NO_RELEVANT_EVIDENCE


async def test_a_candidate_without_evidence_is_refined_then_dropped(maker):
    engine, client = make_engine(
        maker,
        [
            plan_answer(planned()),
            verify_none,
            plan_answer(planned(quran_queries=["خلق السماوات"])),
            verify_none,
            plan_answer(planned(quran_queries=["التفكر"])),
            verify_none,
        ],
    )

    result = await engine.propose(EngineRequest(scan_id="s11", scene=rain_scene()))

    assert result.status is EngineStatus.NO_RELEVANT_EVIDENCE
    stages = [call["stage"].value for call in client.calls]
    assert stages == ["planner", "verify", "planner", "verify", "planner", "verify"]
    assert "refine" in client.calls[2]["user"]


async def test_a_refinement_that_proposes_nothing_ends_the_search(maker):
    engine, _ = make_engine(maker, [plan_answer(planned()), verify_none, plan_answer()])

    result = await engine.propose(EngineRequest(scan_id="s12", scene=rain_scene()))

    assert result.status is EngineStatus.NO_RELEVANT_EVIDENCE


async def test_a_refined_candidate_that_finds_evidence_is_kept(maker):
    engine, _ = make_engine(
        maker,
        [
            plan_answer(planned()),
            verify_none,
            plan_answer(planned(quran_queries=["إحياء الأرض بعد الجفاف"])),
            verify_all(),
            compose_answer(composed()),
        ],
        embedding=False,
    )

    result = await engine.propose(EngineRequest(scan_id="s13", scene=rain_scene()))

    assert result.status is EngineStatus.OK


async def test_two_candidates_on_the_same_texts_make_one_insight(maker):
    engine, _ = make_engine(
        maker,
        [
            plan_answer(planned(), planned(title="ثانية")),
            verify_all(),
            compose_answer(composed(0)),
        ],
    )

    result = await engine.propose(EngineRequest(scan_id="s14", scene=rain_scene()))

    assert len(result.insights) == 1


async def test_a_model_failure_and_a_store_failure_are_told_apart(maker, monkeypatch):
    failing, _ = make_engine(maker, [AiCallError(AiErrorCode.TIMEOUT, "slow")])
    model = await failing.propose(EngineRequest(scan_id="s15", scene=rain_scene()))

    async def broken(*_args: Any, **_kwargs: Any) -> Any:
        raise OperationalError("SELECT 1", {}, Exception("down"))

    monkeypatch.setattr(engine_module, "build_context", broken)
    store, _ = make_engine(maker, [])
    source = await store.propose(EngineRequest(scan_id="s16", scene=rain_scene()))

    assert model.status is EngineStatus.MODEL_UNAVAILABLE
    assert source.status is EngineStatus.SOURCE_UNAVAILABLE


async def test_a_composer_that_keeps_leaking_leaves_no_insight(maker):
    leaking = composed(life=f"قال تعالى: «{verse_text(30, 50)}»")
    engine, _ = make_engine(
        maker,
        [plan_answer(planned()), verify_all(), compose_answer(leaking), compose_answer(leaking)],
    )

    result = await engine.propose(EngineRequest(scan_id="s17", scene=rain_scene()))

    assert result.status is EngineStatus.MODEL_UNAVAILABLE
    assert result.awaiting_ruling


async def test_the_reranker_reorders_and_a_down_reranker_keeps_the_fused_order(maker):
    def scores(request: httpx.Request) -> httpx.Response:
        passages = json.loads(request.content)["passages"]
        return httpx.Response(
            200, json={"scores": [0.1 * i for i in range(len(passages))], "model": "m", "ms": 1}
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(scores))
    reranked, _ = make_engine(
        maker,
        [plan_answer(planned()), verify_all(), compose_answer(composed())],
        reranker=RerankerClient("http://vision", http, timeout_seconds=1),
    )
    down = httpx.AsyncClient(transport=httpx.MockTransport(lambda _r: httpx.Response(503)))
    fused, _ = make_engine(
        maker,
        [plan_answer(planned()), verify_all(), compose_answer(composed())],
        reranker=RerankerClient("http://vision", down, timeout_seconds=1),
    )

    with_scores = await reranked.propose(EngineRequest(scan_id="s18", scene=rain_scene()))
    without = await fused.propose(EngineRequest(scan_id="s19", scene=rain_scene()))

    assert with_scores.insights[0].quran.rerank_score is not None
    assert without.insights[0].quran.rerank_score is None


async def test_the_small_model_reranks_every_list_of_a_scan_at_once(maker):
    def scores(call: dict[str, Any]) -> dict[str, Any]:
        listed = json.loads(call["user"].split("Passages: ", 1)[1])
        return {"passages": [{"number": p["number"], "relevance": 5} for p in listed]}

    small = FakeModelClient(answers=[scores, scores])
    engine, client = make_engine(
        maker,
        [plan_answer(planned()), verify_all(), compose_answer(composed())],
        reranker=LlmReranker(small, model="nano", timeout_seconds=1),
    )

    result = await engine.propose(EngineRequest(scan_id="s24", scene=rain_scene()))

    assert result.insights[0].quran.rerank_score == 0.5
    # One call per searched list (the verse and the hadith), none on the scan's own client.
    assert [call["model"] for call in small.calls] == ["nano", "nano"]
    assert [call["stage"].value for call in client.calls] == ["planner", "verify", "compose"]


async def test_a_failed_query_embedding_falls_back_to_lexical_search(maker):
    engine, client = make_engine(
        maker, [plan_answer(planned()), verify_all(), compose_answer(composed())]
    )
    client.fail_on_call = 1

    result = await engine.propose(EngineRequest(scan_id="s20", scene=rain_scene()))

    assert result.status is EngineStatus.OK


def test_the_engine_is_built_from_the_active_provider(make_settings):
    settings = make_settings(ai_provider=AiProvider.OVH)
    http = httpx.AsyncClient()

    engine = build_engine(settings, http, None)  # type: ignore[arg-type]
    plain = make_settings(ai_ovh={"embedding_model": ""}, ai_provider="ovh")
    without = build_engine(plain, http, None)  # type: ignore[arg-type]

    assert engine._embedding.model == "bge-m3"
    assert without._embedding is None
    # OVH has no rerank model measured: with the default RERANKER=llm it reranks nothing.
    assert engine._reranker is None
    small = build_engine(make_settings(ai_provider="openai"), http, None)  # type: ignore[arg-type]
    assert isinstance(small._reranker, LlmReranker)
    cross = make_settings(reranker="cross_encoder")
    assert isinstance(build_engine(cross, http, None)._reranker, RerankerClient)  # type: ignore[arg-type]
    for off in (
        make_settings(reranker="cross_encoder", reranker_url=""),
        make_settings(reranker="off", ai_provider="openai"),
    ):
        assert build_engine(off, http, None)._reranker is None  # type: ignore[arg-type]
    own = FakeModelClient()
    assert build_engine(settings, http, None, client=own)._client is own  # type: ignore[arg-type]


async def test_a_queued_hadith_is_counted_once_per_scan(maker):
    engine, _ = make_engine(
        maker, [plan_answer(planned()), verify_all(), compose_answer(composed())]
    )

    result = await engine.propose(EngineRequest(scan_id="s21", scene=rain_scene()))

    assert len(result.awaiting_ruling) == len(set(result.awaiting_ruling))
    assert all(ref.collection for ref in result.awaiting_ruling)
    assert RelationType(result.insights[0].relation)


async def test_a_candidate_outside_the_learning_path_searches_without_anchors(maker):
    engine, _ = make_engine(
        maker,
        [plan_answer(planned(learning_unit_id=None)), verify_all(), compose_answer(composed())],
    )

    result = await engine.propose(EngineRequest(scan_id="s23", scene=rain_scene()))

    assert result.insights[0].learning_unit_id is None


@pytest.mark.parametrize("focus", [None, "e1"])
async def test_insights_on_the_focus_come_first(maker, focus):
    engine, _ = make_engine(
        maker, [plan_answer(planned()), verify_all(), compose_answer(composed())]
    )

    result = await engine.propose(
        EngineRequest(scan_id="s22", scene=rain_scene(), focus_entity_id=focus)
    )

    assert result.status is EngineStatus.OK
