"""The pair of texts behind an insight: a waiting hadith, a remote companion, an absent half."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from src.models import EmbeddedCorpus, Hadith, HadithClassification, QuranVerse
from src.pipeline.engine import EngineRequest, EngineStatus, HadithRef, RelationType
from src.pipeline.insight.evidence import Shortlist, TextVerdict, gate
from src.pipeline.insight.planner import PlannedCandidate
from src.pipeline.insight.search import Found
from src.retrieval.documents import RetrievalDocument
from src.scripture.rulings import RulingInput, record_ruling
from tests.insight.support import (
    compose_answer,
    composed,
    plan_answer,
    planned,
    rain_scene,
    verdict,
)
from tests.insight.test_engine import make_engine, verify_all
from tests.scripture.fixtures import enrich_hadith, verse_text

CANDIDATE = PlannedCandidate(
    title="t",
    glimpse="g",
    concept="c",
    value="v",
    relation=RelationType.DIRECT,
    entity_ids=("e1",),
    action_ids=(),
    quran_queries=("q",),
    hadith_queries=("h",),
    ontology_ids=(),
    unit=None,
    content_level="a",
    visible_clues=(),
    limits=(),
)


def _found(corpus: EmbeddedCorpus, key: int) -> Found:
    return Found(corpus, key, 0.5, None, "q", RetrievalDocument(corpus, key, "نص", ()))


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


def _verdicts(**strengths: str) -> dict[str, TextVerdict]:
    return {
        label: TextVerdict.model_validate(verdict(label, strength=strength))
        for label, strength in strengths.items()
    }


async def _gate(session, verse: int, hadiths: list[int], **strengths: str) -> Any:
    shortlist = Shortlist(
        CANDIDATE,
        [_found(EmbeddedCorpus.QURAN, verse)],
        [_found(EmbeddedCorpus.HADITH, key) for key in hadiths],
    )
    return await gate(
        session,
        shortlist,
        _verdicts(**strengths),
        seen_verses=frozenset(),
        seen_hadiths=frozenset(),
    )


async def test_a_wanted_hadith_waiting_for_its_ruling_is_never_replaced_by_another(store):
    verse, wanted, sibling = await _ids(store)
    await _rule(store, sibling, HadithClassification.SAHIH)

    result = await _gate(store, verse, [wanted, sibling], Q1="strong", H1="strong", H2="strong")

    assert result.hadith is None
    assert result.quran is not None
    assert [ref.number for ref in result.awaiting] == [
        await store.scalar(select(Hadith.number).where(Hadith.id == wanted))
    ]


async def test_a_wanted_hadith_of_the_enriched_file_shows_without_waiting_for_a_ruling(store):
    verse, wanted, sibling = await _ids(store)
    await enrich_hadith(store, wanted)
    await _rule(store, sibling, HadithClassification.SAHIH)

    result = await _gate(store, verse, [wanted, sibling], Q1="strong", H1="strong", H2="strong")

    # Decision 58: no ruling, but one of the enriched file's hadiths: it shows, nothing waits.
    assert result.hadith.found.key == wanted
    assert result.awaiting == []


async def test_a_wanted_hadith_ruled_weak_gives_way_to_an_equally_strong_sound_one(store):
    verse, wanted, sibling = await _ids(store)
    await _rule(store, wanted, HadithClassification.DAIF)
    await _rule(store, sibling, HadithClassification.HASAN)

    result = await _gate(store, verse, [wanted, sibling], Q1="strong", H1="strong", H2="strong")

    assert result.hadith.found.key == sibling
    assert result.awaiting == []


async def test_a_remote_text_never_completes_a_pair(store):
    verse, hadith, _ = await _ids(store)
    await _rule(store, hadith, HadithClassification.SAHIH)

    weak_hadith = await _gate(store, verse, [hadith], Q1="strong", H1="weak")
    weak_verse = await _gate(store, verse, [hadith], Q1="weak", H1="medium")
    both_weak = await _gate(store, verse, [hadith], Q1="weak", H1="weak")
    both_strong = await _gate(store, verse, [hadith], Q1="strong", H1="medium")

    assert (weak_hadith.quran is not None, weak_hadith.hadith) == (True, None)
    assert (weak_verse.quran, weak_verse.hadith is not None) == (None, True)
    assert (both_weak.quran is not None, both_weak.hadith) == (True, None)
    assert both_strong.quran is not None and both_strong.hadith is not None
    assert isinstance(both_strong.hadith_ref, HadithRef)


async def test_a_corpus_the_planner_asked_nothing_of_is_not_searched(maker):
    seen: list[dict[str, Any]] = []
    checker = verify_all()

    def recording(call: dict[str, Any]) -> dict[str, Any]:
        seen.append(json.loads(call["user"]))
        return checker(call)

    engine, _ = make_engine(
        maker,
        [plan_answer(planned(hadith_queries=[])), recording, compose_answer(composed(sunnah=None))],
    )

    result = await engine.propose(EngineRequest(scan_id="p1", scene=rain_scene()))

    labels = [text["label"] for text in seen[0]["candidates"][0]["texts"]]
    assert labels and all(label.startswith("Q") for label in labels)
    assert result.insights[0].hadith is None
    assert result.awaiting_ruling == []


async def test_a_scene_question_that_quotes_scripture_is_not_asked(maker):
    engine, _ = make_engine(maker, [plan_answer()])

    result = await engine.propose(
        EngineRequest(scan_id="p2", scene=rain_scene(question=f"«{verse_text(30, 50)}»؟"))
    )

    assert result.status is EngineStatus.NO_RELEVANT_EVIDENCE
    assert result.clarification_question is None
