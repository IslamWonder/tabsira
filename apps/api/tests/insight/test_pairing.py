"""The pair of texts behind an insight: a waiting hadith, a same-tier stand-in, an absent half."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from src.models import EmbeddedCorpus, Hadith, HadithClassification, QuranVerse
from src.pipeline.engine import EngineRequest, EngineStatus, HadithRef, RelationType
from src.pipeline.insight.evidence import PairChoice, Shortlist, TextJudgement, Verdict, gate
from src.pipeline.insight.search import Found
from src.retrieval.documents import RetrievalDocument
from src.scripture.rulings import RulingInput, record_ruling
from tests.insight.support import (
    accept_all,
    composed,
    intent,
    judged,
    plan_answer,
    queries,
    rain_scene,
    shown_labels,
)
from tests.insight.test_engine import make_engine
from tests.insight.test_stages import an_intent
from tests.scripture.fixtures import enrich_hadith, verse_text


def _found(corpus: EmbeddedCorpus, key: int) -> Found:
    return Found(corpus, key, 0.5, key, None, "q", (), RetrievalDocument(corpus, key, "نص", ()))


async def _rule(session, hadith_id: int, classification: HadithClassification) -> None:
    await record_ruling(
        session,
        hadith_id,
        RulingInput(
            ruling_text=classification.value,
            scholar="محرر",
            source_book="كتاب",
            page="1",
            dorar_url="https://dorar.net/hadith/sharh/1",
            classification=classification,
            editor_name="محرر",
        ),
    )


async def _ids(session) -> tuple[int, int, int]:
    verse = await session.scalar(select(QuranVerse.id).where(QuranVerse.surah == 30))
    first, second = (await session.scalars(select(Hadith.id).order_by(Hadith.id).limit(2))).all()
    return verse, first, second


def _verdict(pair: dict[str, Any] | None, **relations: str) -> Verdict:
    judgements = {
        label: TextJudgement.model_validate(
            judged(label, accepted=relation != "rejected", relation=relation)
        )
        for label, relation in relations.items()
    }
    return Verdict(judgements, PairChoice.model_validate(pair) if pair else None)


async def _gate(
    session, verse: int, hadiths: list[int], pair: dict[str, Any] | None = None, **relations: str
) -> Any:
    shortlist = Shortlist(
        an_intent(),
        [_found(EmbeddedCorpus.QURAN, verse)],
        [_found(EmbeddedCorpus.HADITH, key) for key in hadiths],
    )
    return await gate(
        session,
        shortlist,
        _verdict(pair, **relations),
        seen_verses=frozenset(),
        seen_hadiths=frozenset(),
    )


async def test_a_wanted_hadith_waiting_for_its_ruling_is_never_replaced_by_another(store):
    verse, wanted, sibling = await _ids(store)
    await _rule(store, sibling, HadithClassification.SAHIH)
    pair = {"quran": "Q1", "hadith": "H1", "shared_meaning": "م"}

    result = await _gate(
        store, verse, [wanted, sibling], pair, Q1="direct", H1="direct", H2="direct"
    )

    # Decisions 18 and 58: the wanted hadith waits; the insight carries its verse alone.
    assert result.hadith is None
    assert result.quran is not None
    assert result.rejections == {"H1": "awaiting_ruling"}
    assert [ref.number for ref in result.awaiting] == [
        await store.scalar(select(Hadith.number).where(Hadith.id == wanted))
    ]
    assert result.pair_complete is False


async def test_a_wanted_hadith_of_the_enriched_file_shows_without_waiting_for_a_ruling(store):
    verse, wanted, sibling = await _ids(store)
    await enrich_hadith(store, wanted)
    await _rule(store, sibling, HadithClassification.SAHIH)
    pair = {"quran": "Q1", "hadith": "H1", "shared_meaning": "م"}

    result = await _gate(
        store, verse, [wanted, sibling], pair, Q1="direct", H1="direct", H2="direct"
    )

    # Decision 58: no ruling, but one of the enriched file's hadiths: it shows, nothing waits.
    assert result.hadith.found.key == wanted
    assert result.awaiting == []
    assert result.pair_complete


async def test_a_wanted_hadith_ruled_weak_gives_way_to_an_equally_close_sound_one(store):
    verse, wanted, sibling = await _ids(store)
    await _rule(store, wanted, HadithClassification.DAIF)
    await _rule(store, sibling, HadithClassification.HASAN)
    pair = {"quran": "Q1", "hadith": "H1", "shared_meaning": "م"}

    same_tier = await _gate(
        store, verse, [wanted, sibling], pair, Q1="direct", H1="direct", H2="direct"
    )
    weaker = await _gate(
        store, verse, [wanted, sibling], pair, Q1="direct", H1="direct", H2="close_conceptual"
    )

    assert same_tier.hadith.found.key == sibling
    assert same_tier.rejections == {"H1": "ruled_ineligible"}
    assert same_tier.awaiting == []
    # A weaker hadith never stands in: the verse alone, nothing queued.
    assert weaker.hadith is None
    assert weaker.quran is not None
    assert weaker.awaiting == []


async def test_the_server_pairs_only_when_the_verifier_named_no_pair_and_never_across_tiers(
    store,
):
    verse, hadith, other = await _ids(store)
    await _rule(store, hadith, HadithClassification.SAHIH)
    await _rule(store, other, HadithClassification.SAHIH)

    no_pair = await _gate(
        store,
        verse,
        [hadith, other],
        None,
        Q1="close_conceptual",
        H1="direct",
        H2="close_conceptual",
    )
    open_half = await _gate(
        store,
        verse,
        [hadith, other],
        {"quran": "Q1", "hadith": None, "shared_meaning": "م"},
        Q1="direct",
        H1="direct",
        H2="direct",
    )
    hadith_only = await _gate(
        store,
        verse,
        [hadith],
        {"quran": None, "hadith": "H1", "shared_meaning": "م"},
        Q1="direct",
        H1="direct",
    )
    no_same_tier = await _gate(store, verse, [hadith], None, Q1="close_conceptual", H1="direct")
    verse_only = await _gate(store, verse, [hadith], None, Q1="direct", H1="rejected")

    # Without a named pair, the verse leads and a hadith of its own tier follows.
    assert no_pair.hadith.found.key == other
    assert no_pair.shared_meaning == "إحياء الأرض"
    assert isinstance(no_pair.hadith_ref, HadithRef)
    # A half the verifier left open stays open: null means no text serves the shared meaning.
    assert (open_half.quran is not None, open_half.hadith) == (True, None)
    assert (hadith_only.quran, hadith_only.hadith is not None) == (None, True)
    # No hadith of the verse's tier: the verse alone, never a text from another tier.
    assert (no_same_tier.quran is not None, no_same_tier.hadith) == (True, None)
    assert no_same_tier.relation is RelationType.CLOSE_CONCEPTUAL
    assert verse_only.hadith is None
    assert verse_only.rejections == {"H1": "meaning_not_supported"}


async def test_a_corpus_the_planner_asked_nothing_of_is_not_searched(maker):
    seen: list[dict[str, Any]] = []
    checker = accept_all()

    def recording(call: dict[str, Any]) -> dict[str, Any]:
        seen.append(json.loads(call["user"]))
        return checker(call)

    engine, _ = make_engine(
        maker,
        [
            plan_answer(intent(hadith=queries([], []))),
            recording,
            composed(sunnah=None),
        ],
    )

    result = await engine.propose(EngineRequest(scan_id="p1", scene=rain_scene()))

    labels = [text["label"] for text in seen[0]["texts"]]
    assert labels and all(label.startswith("Q") for label in labels)
    assert result.insights[0].hadith is None
    assert result.awaiting_ruling == []
    traced = result.trace["rounds"][0]["intents"][0]
    assert traced["hadith"]["note"] == "not_searched"
    assert traced["gate"]["rejections"] == {"H": "not_searched"}


async def test_the_verifier_may_pair_a_later_verse_with_the_hadith_it_fits(maker):
    chosen: list[str] = []

    def pairing(call: dict[str, Any]) -> dict[str, Any]:
        labels = shown_labels(call)
        verses = [label for label in labels if label.startswith("Q")]
        hadiths = [label for label in labels if label.startswith("H")]
        chosen.append(verses[-1])
        return {
            "texts": [judged(label) for label in labels],
            "pair": {"quran": verses[-1], "hadith": hadiths[0], "shared_meaning": "الماء"},
        }

    engine, client = make_engine(maker, [plan_answer(intent()), pairing, composed()])

    result = await engine.propose(EngineRequest(scan_id="p3", scene=rain_scene()))

    (insight,) = result.insights
    payload = json.loads(client.calls[1]["user"])
    last = payload["texts"][len([t for t in payload["texts"] if t["label"].startswith("Q")]) - 1]
    assert last["label"] == chosen[0]
    assert result.status is EngineStatus.OK
    assert json.loads(client.calls[2]["user"])["insight"]["shared_meaning"] == "الماء"
    assert insight.quran is not None


async def test_a_scene_question_that_quotes_scripture_is_not_asked(maker):
    engine, _ = make_engine(maker, [plan_answer()])

    result = await engine.propose(
        EngineRequest(scan_id="p2", scene=rain_scene(question=f"«{verse_text(30, 50)}»؟"))
    )

    assert result.status is EngineStatus.NO_RELEVANT_EVIDENCE
    assert result.clarification_question is None
