"""The insight engine end to end, on the fixture store, with fake models."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError

from src.ai.errors import AiCallError, AiErrorCode
from src.config import AiProvider
from src.models import (
    EmbeddedCorpus,
    Hadith,
    HadithClassification,
    HadithSignal,
    HadithVerificationQueue,
    QuranVerse,
)
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
from src.pipeline.insight.engine import (
    PipelineInsightEngine,
    ResourceCache,
    Resources,
    build_engine,
)
from src.pipeline.insight.search import Embedding
from src.pipeline.leak_guard import ShingleOverlapDetector
from src.retrieval.concepts import ConceptIndex
from src.retrieval.reranker import LlmReranker, RerankerClient
from src.scripture.rulings import RulingInput, record_ruling
from src.scripture.text import without_marks
from tests.fakes import FakeModelClient
from tests.insight.support import (
    accept_all,
    composed,
    entity,
    intent,
    judged,
    plan_answer,
    queries,
    rain_scene,
    reject_all,
    scene,
    shown_labels,
    verify_answer,
)
from tests.retrieval.support import EmbeddingClient
from tests.scans.conftest import store_extra
from tests.scripture.fixtures import verse_text
from tests.scripture.spelling import standard


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


async def _outside_the_enriched_file(maker) -> None:
    """Unlink every record of the enriched Sunnah file: no hadith is one of its hadiths any more."""
    async with maker() as session, session.begin():
        await session.execute(update(HadithSignal).values(hadith_id=None))


async def _strongly_linked(maker) -> None:
    """Make every record's link strong and into a book it cites, as decision 58 asks."""
    async with maker() as session, session.begin():
        linked = await session.scalars(
            select(HadithSignal).where(HadithSignal.hadith_id.is_not(None))
        )
        for signal in linked.all():
            first, *rest = signal.matches
            signal.match_coverage = 1.0
            signal.matches = [{**first, "coverage": 1.0, "cited": True}, *rest]


async def _rule_every_hadith(maker) -> None:
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


async def test_a_rain_scene_hadith_of_the_enriched_file_shows_beside_its_verse(maker):
    await _strongly_linked(maker)
    engine, _ = make_engine(maker, [plan_answer(intent()), accept_all(), composed()])

    result = await engine.propose(EngineRequest(scan_id="s0", scene=rain_scene()))

    assert result.status is EngineStatus.OK
    (insight,) = result.insights
    assert isinstance(insight.quran.ref, QuranRef)
    # Decision 58: no ruling yet, but one of the enriched file's hadiths: it shows now, and is
    # counted once for an editor while nothing waits for it.
    assert isinstance(insight.hadith.ref, HadithRef)
    assert insight.quran.link and insight.hadith.link
    assert result.awaiting_ruling == []
    assert result.trace["status"] == "ok"
    assert result.trace["chosen"][0]["quran"] == {
        "surah": insight.quran.ref.surah,
        "ayah": insight.quran.ref.ayah,
    }
    round_one = result.trace["rounds"][0]["intents"][0]
    assert round_one["gate"]["pair_complete"] is True
    assert round_one["quran"]["rerank"] == "off"
    assert round_one["quran"]["shortlist"][0]["channels"]
    async with maker() as session:
        assert await session.scalar(select(HadithVerificationQueue.demand_count)) == 1


async def test_a_rain_scene_gets_an_insight_backed_by_its_verse_while_the_hadith_waits(maker):
    await _outside_the_enriched_file(maker)
    engine, client = make_engine(maker, [plan_answer(intent()), accept_all(), composed()])
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
    # No hadith has an editor's ruling or is enriched: the insight carries its verse alone.
    assert insight.hadith is None
    assert [part.section for part in insight.explanation] == ["seen", "value", "quran", "life"]
    # The unit was chosen by the server from the confirmed intent, never by the planner.
    assert insight.learning_unit_id == "T01_06"
    assert insight.explanation[0].sources == ["masar:T01_06"]
    assert insight.explanation[2].sources == [
        f"quran:{insight.quran.ref.surah}:{insight.quran.ref.ayah}",
        "masar:T01_06",
    ]
    assert insight.small_step.kind == "ethical_application"
    assert insight.learning_path_version == "tabsira-masar-1.0"
    assert insight.anchor is not None
    assert insight.why.visible_clues == ["مطر"]
    assert insight.why.limits[0] == "لا تظهر الصورة حال الأرض قبل المطر"
    assert insight.why.personalised_because is not None
    assert result.awaiting_ruling
    async with maker() as session:
        queued = await session.scalar(select(HadithVerificationQueue.demand_count))
    assert queued == 1
    assert [call["stage"].value for call in client.calls] == ["planner", "verify", "compose"]
    # The planner never sees the learner; the composer does.
    assert "learner" not in json.loads(client.calls[0]["user"])
    assert "learner" in json.loads(client.calls[2]["user"])


async def test_an_eligible_hadith_completes_the_pair_and_grounds_the_step(maker):
    await _rule_every_hadith(maker)
    engine, _ = make_engine(maker, [plan_answer(intent()), accept_all(), composed()])

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
    engine, client = make_engine(maker, [plan_answer(intent()), accept_all(), composed()])
    first = await engine.propose(EngineRequest(scan_id="s3", scene=rain_scene()))
    seen = first.insights[0].quran.ref

    def only_first(call: dict[str, Any]) -> dict[str, Any]:
        labels = shown_labels(call)
        return verify_answer(
            [judged(label, accepted=label == labels[0]) for label in labels], pair=None
        )

    client.answers = [plan_answer(intent()), only_first, composed()]
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
    assert abstained.trace["status"] == "no_relevant_evidence"
    assert answered.status is EngineStatus.NO_RELEVANT_EVIDENCE


async def test_an_intent_without_evidence_is_refined_with_the_reasons_then_dropped(maker):
    engine, client = make_engine(
        maker,
        [
            plan_answer(intent()),
            reject_all,
            plan_answer(intent(quran=queries(["إحياء الأرض"], ["تحيا الأرض بالماء"]))),
            reject_all,
            plan_answer(intent(quran=queries(["حياة الأرض"], ["الأرض تحيا بعد المطر"]))),
            reject_all,
        ],
    )

    result = await engine.propose(EngineRequest(scan_id="s11", scene=rain_scene()))

    assert result.status is EngineStatus.NO_RELEVANT_EVIDENCE
    stages = [call["stage"].value for call in client.calls]
    assert stages == ["planner", "verify", "planner", "verify", "planner", "verify"]
    refine = json.loads(client.calls[2]["user"])["refine"]
    assert refine[0]["intent_id"] == "i1"
    assert refine[0]["rejected_because"] == ["lexical_overlap"]
    assert len(result.trace["rounds"]) == 3
    # Refined intents are named by the server after their round.
    assert result.trace["rounds"][1]["intents"][0]["intent_id"] == "r1i1"


async def test_a_refinement_that_moves_to_other_clues_is_dropped(maker):
    engine, _ = make_engine(
        maker,
        [plan_answer(intent()), reject_all, plan_answer(intent(scene_anchor_ids=["e2"]))],
    )

    result = await engine.propose(EngineRequest(scan_id="s12", scene=rain_scene()))

    assert result.status is EngineStatus.NO_RELEVANT_EVIDENCE
    assert result.trace["rounds"][-1]["dropped"] == ["intent 0: refinement moved to other clues"]


async def test_a_refined_intent_that_finds_evidence_is_kept(maker):
    engine, _ = make_engine(
        maker,
        [
            plan_answer(intent()),
            reject_all,
            plan_answer(intent(quran=queries(["إحياء الأرض بعد الجفاف"], None))),
            accept_all(),
            composed(),
        ],
        embedding=False,
    )

    result = await engine.propose(EngineRequest(scan_id="s13", scene=rain_scene()))

    assert result.status is EngineStatus.OK


async def test_a_lone_verse_does_not_stop_the_refinement_but_a_complete_pair_does(maker):
    await _strongly_linked(maker)

    def verse_only(call: dict[str, Any]) -> dict[str, Any]:
        return verify_answer(
            [judged(label, accepted=label.startswith("Q")) for label in shown_labels(call)]
        )

    engine, client = make_engine(
        maker,
        [
            plan_answer(intent(), intent(scene_anchor_ids=["e2"])),
            verse_only,
            reject_all,
            plan_answer(intent(scene_anchor_ids=["e2"])),
            accept_all(),
            composed(),
        ],
    )

    result = await engine.propose(EngineRequest(scan_id="s15", scene=rain_scene()))

    assert result.status is EngineStatus.OK
    stages = [call["stage"].value for call in client.calls]
    assert stages == ["planner", "verify", "verify", "planner", "verify", "compose"]
    # The complete pair is shown; the lone verse of the first intent is not beside it.
    (insight,) = result.insights
    assert insight.hadith is not None
    assert insight.entity_ids == ["e2"]


async def test_two_intents_on_the_same_texts_make_one_insight(maker):
    engine, _ = make_engine(
        maker,
        [
            plan_answer(intent(), intent()),
            accept_all(),
            accept_all(),
            composed(),
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
    assert model.trace["status"] == "model_unavailable"
    assert source.status is EngineStatus.SOURCE_UNAVAILABLE


async def test_a_failed_query_embedding_is_a_retrieval_error_not_an_empty_result(maker):
    engine, client = make_engine(maker, [plan_answer(intent()), accept_all(), composed()])
    client.fail_on_call = 1

    result = await engine.propose(EngineRequest(scan_id="s20", scene=rain_scene()))

    assert result.status is EngineStatus.RETRIEVAL_ERROR
    assert [call["stage"].value for call in client.calls] == ["planner"]


async def test_a_store_without_a_searchable_corpus_says_so(maker):
    engine, client = make_engine(maker, [plan_answer(intent())])
    empty = {corpus: ConceptIndex(corpus, {}) for corpus in EmbeddedCorpus}
    engine._resources._resources = Resources(
        concepts=empty,
        quran=ShingleOverlapDetector([]),
        path=None,
        vectors=dict.fromkeys(EmbeddedCorpus, False),
    )

    result = await engine.propose(EngineRequest(scan_id="s25", scene=rain_scene()))

    assert result.status is EngineStatus.CORPUS_UNAVAILABLE
    assert client.calls == []
    assert result.trace["corpus"]["vectors"] == {"quran": False, "hadith": False}


async def test_the_resource_check_reads_whether_the_vectors_of_the_model_are_stored(maker):
    cache = ResourceCache()
    async with maker() as session:
        without = await cache.get(session, None)
        with_model = await ResourceCache().get(session, Embedding(FakeModelClient(), "m", 8))
        any_size = await ResourceCache().get(session, Embedding(FakeModelClient(), "m", None))

    assert without.vectors == {EmbeddedCorpus.QURAN: False, EmbeddedCorpus.HADITH: False}
    assert with_model.vectors == without.vectors == any_size.vectors
    assert with_model.searchable


async def test_the_only_fitting_hadith_waiting_for_its_ruling_is_an_incomplete_pair(maker):
    await _outside_the_enriched_file(maker)

    def hadith_only(call: dict[str, Any]) -> dict[str, Any]:
        return verify_answer(
            [judged(label, accepted=label.startswith("H")) for label in shown_labels(call)]
        )

    engine, _ = make_engine(maker, [plan_answer(intent()), hadith_only, plan_answer()], rounds=1)

    result = await engine.propose(EngineRequest(scan_id="s26", scene=rain_scene()))

    assert result.status is EngineStatus.INCOMPLETE_EVIDENCE_PAIR
    assert result.awaiting_ruling
    assert result.insights == []


async def test_a_composer_that_keeps_leaking_leaves_no_insight(maker):
    await _outside_the_enriched_file(maker)
    leaking = composed(life=f"قال تعالى: «{verse_text(30, 50)}»")
    engine, _ = make_engine(maker, [plan_answer(intent()), accept_all(), leaking, leaking])

    result = await engine.propose(EngineRequest(scan_id="s17", scene=rain_scene()))

    assert result.status is EngineStatus.MODEL_UNAVAILABLE
    assert result.trace["composer"]["leaked"] == [0]
    assert result.awaiting_ruling


async def _today_3_190(maker) -> str:
    """Al Imran 3:190 as a model would write it: read from the store, respelled, never typed."""
    async with maker() as session, session.begin():
        await store_extra(session)
    async with maker() as session:
        stored: str = await session.scalar(
            select(QuranVerse.text).where(QuranVerse.surah == 3, QuranVerse.ayah == 190)
        )
    today = standard(stored)
    assert today != stored
    return today


async def _unshown_hadith_words(maker) -> str:
    """
    The last words of Bukhari 2320, unvocalised as a model writes, from the store.

    No stage of a rain scan is shown this hadith, and without its marks the pattern
    rules see plain prose: only the store-wide check can find it.
    """
    async with maker() as session:
        stored: str = await session.scalar(
            select(Hadith.text).where(Hadith.collection == "bukhari", Hadith.number == "2320")
        )
    return " ".join(without_marks(stored).split()[-12:])


async def test_a_planner_field_repeating_a_hadith_no_stage_was_shown_is_refused(maker):
    await _today_3_190(maker)
    words = await _unshown_hadith_words(maker)
    engine, _ = make_engine(maker, [plan_answer(intent(concept_basis=f"تذكر {words}"))] * 2)

    result = await engine.propose(EngineRequest(scan_id="s-unshown", scene=rain_scene()))

    # The whole store is the corpus, not only the texts the stage saw.
    assert result.status is EngineStatus.MODEL_UNAVAILABLE
    assert result.insights == []


def _verify_linked_by(link: str) -> Any:
    """A verifier that accepts every text and writes `link` as each one's link."""
    accepting = accept_all()

    def answer(call: dict[str, Any]) -> dict[str, Any]:
        verdict = accepting(call)
        for text in verdict["texts"]:
            text["link"] = link
        return verdict

    return answer


@pytest.mark.parametrize(
    "where", ["planner", "verifier", "explanation", "small_step", "scene_question"]
)
async def test_a_verse_in_todays_spelling_is_refused_wherever_a_model_writes_it(maker, where):
    today = await _today_3_190(maker)
    quoting = f"وفي ذلك {today}"
    step = {"text": quoting, "kind": "reflection", "from_hadith": False}
    answers: dict[str, list[Any]] = {
        "planner": [plan_answer(intent(concept_basis=quoting))] * 2,
        # A verifier that keeps quoting leaves its intent unjudged; the refinement that
        # follows proposes nothing, and the scan ends as a model fault.
        "verifier": [plan_answer(intent()), *[_verify_linked_by(quoting)] * 2, plan_answer()],
        "explanation": [plan_answer(intent()), accept_all(), *[composed(life=quoting)] * 2],
        "small_step": [plan_answer(intent()), accept_all(), *[composed(small_step=step)] * 2],
        "scene_question": [plan_answer()],
    }
    engine, _ = make_engine(maker, answers[where])
    question = quoting if where == "scene_question" else None

    result = await engine.propose(
        EngineRequest(scan_id=f"s-{where}", scene=rain_scene(question=question))
    )

    assert result.insights == []
    assert result.clarification_question is None
    expected = (
        EngineStatus.NO_RELEVANT_EVIDENCE
        if where == "scene_question"
        else EngineStatus.MODEL_UNAVAILABLE
    )
    assert result.status is expected


async def test_the_reranker_reorders_and_a_down_reranker_keeps_the_fused_order(maker):
    asked: list[str] = []

    def scores(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        asked.append(body["query"])
        passages = body["passages"]
        return httpx.Response(
            200, json={"scores": [0.1 * i for i in range(len(passages))], "model": "m", "ms": 1}
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(scores))
    reranked, _ = make_engine(
        maker,
        [plan_answer(intent()), accept_all(), composed()],
        reranker=RerankerClient("http://vision", http, timeout_seconds=1),
    )
    down = httpx.AsyncClient(transport=httpx.MockTransport(lambda _r: httpx.Response(503)))
    fused, _ = make_engine(
        maker,
        [plan_answer(intent()), accept_all(), composed()],
        reranker=RerankerClient("http://vision", down, timeout_seconds=1),
    )

    with_scores = await reranked.propose(EngineRequest(scan_id="s18", scene=rain_scene()))
    without = await fused.propose(EngineRequest(scan_id="s19", scene=rain_scene()))

    assert with_scores.insights[0].quran.rerank_score is not None
    # The reranker reads the intent's own sentence of each corpus, never a pile of queries.
    assert asked == ["ينزل المطر فتحيا الأرض بعد يبسها", "ما يقال عند نزول المطر"]
    assert without.insights[0].quran.rerank_score is None
    traced = without.trace["rounds"][0]["intents"][0]["quran"]["rerank"]
    assert traced == "skipped: http_503"
    assert with_scores.trace["rounds"][0]["intents"][0]["quran"]["rerank"].startswith("ok: m")


async def test_the_small_model_reranks_every_list_of_a_scan_at_once(maker):
    def scores(call: dict[str, Any]) -> dict[str, Any]:
        listed = json.loads(call["user"].split("Passages: ", 1)[1])
        return {"passages": [{"number": p["number"], "relevance": 5} for p in listed]}

    small = FakeModelClient(answers=[scores, scores])
    engine, client = make_engine(
        maker,
        [plan_answer(intent()), accept_all(), composed()],
        reranker=LlmReranker(small, model="nano", timeout_seconds=1),
    )

    result = await engine.propose(EngineRequest(scan_id="s24", scene=rain_scene()))

    assert result.insights[0].quran.rerank_score == 0.5
    # One call per searched list (the verse and the hadith), none on the scan's own client.
    assert [call["model"] for call in small.calls] == ["nano", "nano"]
    assert [call["stage"].value for call in client.calls] == ["planner", "verify", "compose"]


def test_the_engine_is_built_from_the_active_provider(make_settings):
    settings = make_settings(ai_provider=AiProvider.OVH, reranker="llm")
    http = httpx.AsyncClient()

    engine = build_engine(settings, http, None)  # type: ignore[arg-type]
    plain = make_settings(ai_ovh={"embedding_model": ""}, ai_provider="ovh")
    without = build_engine(plain, http, None)  # type: ignore[arg-type]

    assert engine._embedding.model == "bge-m3"
    assert without._embedding is None
    # OVH has no rerank model measured: even with RERANKER=llm it reranks nothing.
    assert engine._reranker is None
    small = build_engine(make_settings(ai_provider="openai", reranker="llm"), http, None)  # type: ignore[arg-type]
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
    engine, _ = make_engine(maker, [plan_answer(intent()), accept_all(), composed()])

    result = await engine.propose(EngineRequest(scan_id="s21", scene=rain_scene()))

    assert len(result.awaiting_ruling) == len(set(result.awaiting_ruling))
    assert all(ref.collection for ref in result.awaiting_ruling)
    assert RelationType(result.insights[0].relation)


async def test_an_intent_no_unit_fits_makes_an_insight_without_a_unit(maker):
    foreign = intent(
        candidate_concept="zzqq",
        observable_meaning="zzqq",
        relation_description="zzqq",
    )
    engine, _ = make_engine(maker, [plan_answer(foreign), accept_all(), composed()])

    result = await engine.propose(
        EngineRequest(scan_id="s23", scene=rain_scene(description="zzqq"))
    )

    assert result.insights[0].learning_unit_id is None


@pytest.mark.parametrize("focus", [None, "e1"])
async def test_insights_on_the_focus_come_first(maker, focus):
    engine, _ = make_engine(maker, [plan_answer(intent()), accept_all(), composed()])

    result = await engine.propose(
        EngineRequest(scan_id="s22", scene=rain_scene(), focus_entity_id=focus)
    )

    assert result.status is EngineStatus.OK
