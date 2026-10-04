"""The engine's stages one by one: the branches the end-to-end tests do not reach."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from src.models import EmbeddedCorpus, QuranVerse
from src.pipeline.engine import (
    EngineRequest,
    ExplanationPart,
    HadithRef,
    LearnerContext,
    QuranRef,
    RelationType,
    SmallStep,
)
from src.pipeline.insight.composer import (
    ComposedInsight,
    InsightComposer,
    allowed_references,
    build_insight,
    citation,
    cites_only_its_own,
)
from src.pipeline.insight.context import SceneContext, build_context
from src.pipeline.insight.engine import scene_texts
from src.pipeline.insight.evidence import (
    Chosen,
    GateResult,
    Shortlist,
    VerifierLeakError,
    pick,
    seen_ids,
    verify,
)
from src.pipeline.insight.guard import (
    STORE_FINDING,
    EngineGuard,
    scripture_guard,
    without_honorific,
)
from src.pipeline.insight.learning import (
    LearningPath,
    RankedInsight,
    Unit,
    UnitOption,
    domain_counts,
    load_path,
    personalised_reason,
    rank_key,
    unit_options,
)
from src.pipeline.insight.planner import InsightPlanner, PlannedCandidate, PlannerLeakError
from src.pipeline.insight.search import Embedding, EvidenceSearch, Found, embed_queries
from src.pipeline.leak_guard import LeakGuard
from src.pipeline.schemas import EvidenceStatus, SceneAction
from src.retrieval.concepts import ConceptIndex
from src.retrieval.documents import RetrievalDocument
from src.scripture.text import without_marks
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
)
from tests.retrieval.support import EmbeddingClient
from tests.scripture.fixtures import hadith_text, verse_text


def candidate(**fields: Any) -> PlannedCandidate:
    return PlannedCandidate(
        **(
            {
                "title": "عنوان",
                "glimpse": "لمحة",
                "concept": "إحياء الأرض",
                "value": "رحمة",
                "relation": RelationType.DIRECT,
                "entity_ids": ("e1",),
                "action_ids": (),
                "quran_queries": ("إحياء الأرض",),
                "hadith_queries": (),
                "ontology_ids": (),
                "unit": None,
                "content_level": "a",
                "visible_clues": (),
                "limits": (),
            }
            | fields
        )
    )


def found(key: int, corpus: EmbeddedCorpus = EmbeddedCorpus.QURAN, text: str = "نص") -> Found:
    return Found(corpus, key, 0.5, None, "إحياء الأرض", RetrievalDocument(corpus, key, text, ()))


def chosen(key: int, *, review: bool = False) -> Chosen:
    return Chosen(found(key), RelationType.DIRECT, "حد", review=review, unseen_preferred=False)


# ─── Context ───


async def test_context_names_blocks_questions_and_deduplicated_concepts(store):
    hand_and_unknown = scene(
        [
            entity("e1", "hand", "يد"),
            entity("e2", "zzqq", "شيء غامض جدا"),
            entity("e3", "rain", "مطر"),
        ]
    )

    context = await build_context(store, hand_and_unknown, clarified=False)
    empty = await build_context(store, scene([]), clarified=False)

    assert context.blocked == {"e1"}
    assert context.rules
    assert "e2" in context.to_clarify
    assert context.question_for(["e3", "e2"]) == context.to_clarify["e2"].question
    assert context.question_for(["e3"]) is None
    assert context.unusable(["e1", "e2"])
    assert not context.unusable(["e3"])
    assert context.unusable(["e9"])
    concepts = context.entities["e3"].concepts()
    assert len(concepts) == len(set(concepts))
    assert empty.entities == {}


# ─── Learning path ───


def _path() -> LearningPath:
    def unit(unit_id: str, domain: str, prerequisites: tuple[str, ...] = ()) -> Unit:
        return Unit(unit_id, domain, f"وحدة {unit_id}", (), prerequisites, (), frozenset({"مطر"}))

    return LearningPath(
        "v1",
        {"A": unit("A", "T01"), "B": unit("B", "T01", ("A",)), "C": unit("C", "T02")},
    )


def test_unit_options_mark_completed_and_ready_units_and_ignore_history_when_off():
    path = _path()
    learner = LearnerContext(completed_units=["A"])

    options = {o.unit.unit_id: o for o in unit_options(path, ["المطر"], learner)}
    private = unit_options(
        path, ["المطر"], learner.model_copy(update={"personalization_enabled": False})
    )

    assert options["A"].completed and options["B"].ready
    assert not any(option.completed for option in private)
    assert unit_options(path, ["سيارة"], learner) == []
    assert domain_counts(path, LearnerContext(completed_units=["A", "Z"])) == {"T01": 1}


def test_masar_order_puts_focus_relation_next_step_novelty_and_coverage_in_turn():
    ready = UnitOption(_path().units["B"], completed=False, ready=True, match=1)
    items = [
        RankedInsight(False, RelationType.DIRECT, None, 0, 0),
        RankedInsight(True, RelationType.THEMATIC_REMINDER, None, 0, 0),
        RankedInsight(False, RelationType.DIRECT, ready, 0, 0),
        RankedInsight(False, RelationType.OPPOSITE, None, 2, 0),
    ]

    ordered = sorted(items, key=rank_key)

    assert ordered[0].on_focus
    assert ordered[1].unit is ready
    assert ordered[-1].relation is RelationType.OPPOSITE


def test_the_personal_reason_is_honest_about_what_was_used():
    learner = LearnerContext(completed_units=["A"])
    path = _path()
    done = UnitOption(path.units["A"], completed=True, ready=True, match=1)
    next_step = UnitOption(path.units["B"], completed=False, ready=True, match=1)
    plain = UnitOption(path.units["C"], completed=False, ready=True, match=1)

    assert personalised_reason(None, learner, review=True, new_text=False)
    assert personalised_reason(None, learner, review=False, new_text=True)
    assert "وحدة A" in (personalised_reason(done, learner, review=False, new_text=False) or "")
    assert personalised_reason(next_step, learner, review=False, new_text=False)
    assert personalised_reason(plain, learner, review=False, new_text=False) is None
    assert personalised_reason(None, LearnerContext(), review=False, new_text=False)
    off = LearnerContext(personalization_enabled=False)
    assert personalised_reason(None, off, review=True, new_text=False) is None


async def test_no_active_learning_path_offers_no_unit(db_session):
    assert await load_path(db_session) is None


def test_scene_texts_include_the_answer_the_person_gave():
    request = EngineRequest(scan_id="s", scene=rain_scene(), clarification_answer="أقصد المطر")

    assert "أقصد المطر" in scene_texts(request, SceneContext({}))


# ─── Planner ───


async def test_the_planner_checks_every_candidate_against_the_scene(store):
    shown = SceneAction(
        id="a1",
        label="يسقي",
        actor_ids=["e1"],
        target_ids=["e2"],
        visible_evidence=["ماء"],
        status=EvidenceStatus.INFERRED,
    )
    seen = scene(
        [entity("e1", "rain", "مطر", EvidenceStatus.INFERRED), entity("e2", "hand", "يد")],
        actions=[shown],
    )
    context = await build_context(store, seen, clarified=False)
    client = FakeModelClient(
        answers=[
            plan_answer(
                planned(relation="action_based", action_ids=["a1", "a9"]),
                planned(relation="direct", entity_ids=["e1", "e9"]),
                planned(entity_ids=["e2"]),
                planned(quran_queries=[], hadith_queries=["كلمة " * 20]),
                needs_clarification=True,
                clarification_question="ماذا تقصد؟",
                unknown_concepts=["مفهوم جديد", " "],
            )
        ]
    )
    request = EngineRequest(
        scan_id="s",
        scene=seen,
        max_insights=3,
        learner=LearnerContext(goals=["reflection"], knowledge_level="beginner"),
    )

    plan = await InsightPlanner(client).plan(request, context, [], EngineGuard(LeakGuard(), None))

    assert [c.relation for c in plan.candidates] == [
        RelationType.CLOSE_CONCEPTUAL,
        RelationType.CLOSE_CONCEPTUAL,
    ]
    assert plan.candidates[0].action_ids == ("a1",)
    assert plan.candidates[1].entity_ids == ("e1",)
    assert plan.dropped == ["candidate 2: rests only on blocked or unanswered entities"]
    assert plan.question == "ماذا تقصد؟"
    assert plan.unknown_concepts == ["مفهوم جديد"]
    assert '"goals": ["reflection"]' in client.calls[0]["user"]
    assert plan.candidates[0].unit is None


async def test_the_planner_drops_candidates_off_the_focus_or_without_queries(store):
    context = await build_context(store, rain_scene(), clarified=False)
    client = FakeModelClient(
        answers=[
            plan_answer(
                planned(entity_ids=["e2"]),
                planned(quran_queries=[], hadith_queries=[]),
            )
        ]
    )
    request = EngineRequest(scan_id="s", scene=rain_scene(), focus_entity_id="e1")

    plan = await InsightPlanner(client).plan(request, context, [], EngineGuard(LeakGuard(), None))

    assert plan.candidates == []
    assert plan.dropped == ["candidate 0: not about the focus", "candidate 1: no usable query"]
    assert plan.question is None


async def test_a_leaking_plan_is_asked_again_then_refused(store):
    context = await build_context(store, rain_scene(), clarified=False)
    leaking = plan_answer(planned(glimpse=f"قال تعالى: «{verse_text(30, 50)}»"))
    request = EngineRequest(scan_id="s", scene=rain_scene())

    recovered = await InsightPlanner(
        FakeModelClient(answers=[leaking, plan_answer(planned())])
    ).plan(request, context, [], EngineGuard(LeakGuard(), None))
    with pytest.raises(PlannerLeakError):
        await InsightPlanner(FakeModelClient(answers=[leaking, leaking])).plan(
            request, context, [], EngineGuard(LeakGuard(), None)
        )

    assert len(recovered.candidates) == 1


# ─── Search ───


async def test_query_embedding_is_one_call_and_its_failure_is_a_reason():
    client = EmbeddingClient()

    vectors, error = await embed_queries(Embedding(client, "m", 8), ["أ", "ب", "أ"])
    nothing = await embed_queries(None, ["أ"])
    empty = await embed_queries(Embedding(client, "m", 8), [])
    client.fail_on_call = 2
    failed = await embed_queries(Embedding(client, "m", 8), ["أ"])

    assert (list(vectors), error) == (["أ", "ب"], None)
    assert nothing == ({}, None) == empty
    assert failed == ({}, "timeout")


async def test_a_search_that_finds_nothing_returns_nothing(store):
    index = ConceptIndex(EmbeddedCorpus.QURAN, {})
    search = EvidenceSearch(embedding=None, reranker=None, concepts={EmbeddedCorpus.QURAN: index})

    found = await search.search(store, EmbeddedCorpus.QURAN, ["زززز"], {})
    reranked = await search.rerank(["زززز"], found)

    assert found == reranked.found == []


async def test_anchors_alone_name_their_texts(store):
    verse = await store.scalar(select(QuranVerse.id).where(QuranVerse.surah == 112))
    index = ConceptIndex(EmbeddedCorpus.QURAN, {})
    search = EvidenceSearch(embedding=None, reranker=None, concepts={EmbeddedCorpus.QURAN: index})

    found = await search.search(store, EmbeddedCorpus.QURAN, ["زززز"], {}, anchors=[verse])

    assert [item.key for item in found] == [verse]
    assert found[0].matched_on == "زززز"


# ─── Evidence ───


async def test_the_verifier_keeps_known_labels_of_known_candidates_only():
    shortlist = Shortlist(candidate(), [found(1)], [found(2, EmbeddedCorpus.HADITH)])
    client = FakeModelClient(
        answers=[
            {
                "candidates": [
                    {"candidate": 0, "texts": [verdict("Q1"), verdict("Q7"), verdict("H1")]},
                    {"candidate": 5, "texts": [verdict("Q1")]},
                ]
            }
        ]
    )

    verdicts = await verify(client, rain_scene(), [shortlist], EngineGuard(LeakGuard(), None))

    assert set(verdicts) == {0}
    assert set(verdicts[0]) == {"Q1", "H1"}


async def test_a_leaking_verifier_is_asked_again_then_refused():
    leaking = {
        "candidates": [
            {
                "candidate": 0,
                "texts": [verdict("Q1") | {"limit": f"قال تعالى: «{verse_text(30, 50)}»"}],
            }
        ]
    }
    shortlist = Shortlist(candidate(), [found(1)], [])

    with pytest.raises(VerifierLeakError):
        await verify(
            FakeModelClient(answers=[leaking, leaking]),
            rain_scene(),
            [shortlist],
            EngineGuard(LeakGuard(), None),
        )


def test_pick_prefers_an_unseen_text_of_the_strongest_tier_and_reviews_otherwise():
    strong = verdict("Q1")
    weak = verdict("Q2", strength="weak")
    texts = [(found(1), _verdict(strong)), (found(2), _verdict(strong)), (found(3), _verdict(weak))]

    fresh = pick(texts, frozenset({1}))
    review = pick(texts, frozenset({1, 2}))

    assert (fresh.found.key, fresh.review, fresh.unseen_preferred) == (2, False, True)
    assert (review.found.key, review.review) == (1, True)
    assert pick([], frozenset()) is None


def _verdict(answer: dict[str, Any]) -> Any:
    from src.pipeline.insight.evidence import TextVerdict

    return TextVerdict.model_validate(answer)


async def test_seen_texts_are_found_by_reference_unless_personalisation_is_off(store):
    learner = LearnerContext(
        seen_quran=[QuranRef(surah=30, ayah=50)],
        seen_hadith=[HadithRef(collection="bukhari", number="1032")],
    )

    verses, hadiths = await seen_ids(store, learner)
    off = await seen_ids(store, learner.model_copy(update={"personalization_enabled": False}))

    assert len(verses) == len(hadiths) == 1
    assert off == (frozenset(), frozenset())


# ─── Composer and guard ───


def test_a_personal_matter_ends_with_the_referral_and_steps_keep_their_kind():
    result = GateResult(
        candidate(content_level="d"), quran=chosen(1), quran_ref=QuranRef(surah=1, ayah=1)
    )
    base = composed(sunnah=None)

    referred = build_insight(
        ComposedInsight.model_validate(base), result, rain_scene(), LearnerContext(), None
    )
    reflection = build_insight(
        ComposedInsight.model_validate(
            base | {"small_step": {"text": "تأمل", "kind": "reflection", "from_hadith": False}}
        ),
        result,
        scene([entity("e1", "x", "شيء")]),
        LearnerContext(),
        None,
    )
    stepless = build_insight(
        ComposedInsight.model_validate(
            base | {"small_step": {"text": " ", "kind": "reflection", "from_hadith": False}}
        ),
        result,
        rain_scene(),
        LearnerContext(),
        None,
    )

    assert referred.explanation[-1].text.endswith("المؤهلين.")
    assert referred.small_step.kind == "ethical_application"
    assert reflection.small_step.kind == "reflection"
    assert reflection.anchor is None
    assert stepless.small_step is None
    assert referred.learning_path_version is None


async def test_the_composer_drops_an_insight_that_keeps_leaking_and_ignores_unknown_indexes():
    leaking = composed(1, value=f"قال تعالى: «{verse_text(30, 50)}»")
    results = [
        GateResult(candidate(), quran=chosen(1), quran_ref=QuranRef(surah=1, ayah=1)),
        GateResult(candidate(), quran=chosen(2), quran_ref=QuranRef(surah=1, ayah=2)),
    ]
    client = FakeModelClient(
        answers=[
            compose_answer(composed(0, small_step=None), leaking, composed(9)),
            compose_answer(leaking),
        ]
    )

    composition = await InsightComposer(client).compose(
        rain_scene(), results, LearnerContext(), EngineGuard(LeakGuard(), None), "v1"
    )

    assert len(composition.insights) == 1
    assert composition.leaked == [1]
    assert len(client.calls) == 2


async def test_the_guard_compares_with_the_hadiths_shown_without_the_honorific():
    text = hadith_text("bukhari", 1032)
    guard = scripture_guard(None, [text])

    assert without_honorific("قال النبي صلى الله عليه وسلم") == without_honorific("قال النبي")
    assert await guard.leaks([text])
    assert not await guard.leaks(["يعلمنا النبي صلى الله عليه وسلم أدب الدعاء عند المطر"])
    assert not await scripture_guard(None).leaks(["نص عادي عن المطر والأرض"])


async def test_the_store_wide_check_names_only_the_field_that_repeats_a_stored_text(store):
    # Unvocalised, as a model writes: the pattern rules alone see plain prose.
    words = " ".join(without_marks(hadith_text("bukhari", 1032)).split()[-12:])
    guard = scripture_guard(None, session=store)

    refused = await guard.refused({"plain": "نص عادي عن المطر والأرض", "copied": f"تذكر {words}"})

    assert list(refused) == ["copied"]
    assert refused["copied"].findings == [STORE_FINDING]
    assert await guard.leaks([f"تذكر {words}"])
    assert await scripture_guard(None).refused({"copied": f"تذكر {words}"}) == {}


def test_a_hadith_alone_makes_an_insight_without_a_verse_part():
    hadith = Chosen(
        found(5, EmbeddedCorpus.HADITH),
        RelationType.ACTION_BASED,
        "",
        review=False,
        unseen_preferred=False,
    )
    result = GateResult(
        candidate(), hadith=hadith, hadith_ref=HadithRef(collection="bukhari", number="1")
    )
    item = ComposedInsight.model_validate(composed(small_step=None))

    insight = build_insight(item, result, rain_scene(), LearnerContext(), None)

    assert insight.quran is None
    assert [part.section for part in insight.explanation] == ["seen", "value", "sunnah", "life"]
    assert insight.explanation[2].sources == ["hadith:bukhari:1"]
    assert insight.small_step is None
    assert insight.relation is RelationType.ACTION_BASED
    assert cites_only_its_own(insight)


def test_an_insight_citing_anything_but_its_own_texts_and_unit_is_refused():
    result = GateResult(candidate(), quran=chosen(1), quran_ref=QuranRef(surah=30, ayah=50))
    built = build_insight(
        ComposedInsight.model_validate(composed()), result, rain_scene(), LearnerContext(), None
    )
    other_text = built.model_copy(
        update={"explanation": [ExplanationPart(section="value", text="ش", sources=["quran:2:1"])]}
    )
    free_form = built.model_copy(
        update={"explanation": [ExplanationPart(section="value", text="ش", sources=["تفسير"])]}
    )
    unit_as_ground = built.model_copy(
        update={
            "learning_unit_id": "T01_06",
            "small_step": SmallStep(
                text="خطوة", kind="text_grounded", grounded_in=["masar:T01_06"]
            ),
        }
    )

    assert allowed_references(built) == {"quran:30:50"}
    assert cites_only_its_own(built)
    assert not cites_only_its_own(other_text)
    assert not cites_only_its_own(free_form)
    assert not cites_only_its_own(unit_as_ground)
    assert citation(HadithRef(collection="muslim", number="93")) == "hadith:muslim:93"
