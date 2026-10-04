"""No scripture from a model, and no insight with nothing to show."""

from __future__ import annotations

import pytest

from src.models import HadithClassification
from src.pipeline.engine import ExplanationPart, SmallStep
from src.scans.accept import accept
from src.scripture import overlap
from src.scripture.text import search_copy
from tests.scans.builders import hadith, insight_row, proposed, scan_row, scene
from tests.scans.conftest import as_guest, rule
from tests.scans.test_chat import an_insight, ask, said
from tests.scripture.fixtures import hadith_text, verse_text


def words_of(text: str, start: int, count: int) -> str:
    """Plain words of a stored text, as a model would copy them without any mark."""
    return " ".join(search_copy(text).split()[start : start + count])


def explained(text: str) -> list[ExplanationPart]:
    return [ExplanationPart(section="value", text=text)]


async def test_a_text_of_the_store_copied_without_any_mark_is_refused(store):
    elsewhere = words_of(verse_text(2, 49), 2, 8)
    weak = words_of(hadith_text("bukhari", 8), 4, 6)
    async with store() as db:
        await rule(db, "bukhari", "8", HadithClassification.DAIF)
        accepted = await accept(
            db,
            scene(),
            [
                proposed(explanation=explained(f"وفي معنى ذلك {elsewhere}.")),
                proposed(hadith=hadith("bukhari", "8"), explanation=explained(f"وكما ورد {weak}.")),
                proposed(explanation=explained("الماء نعمة تُرى آثارها في الأرض والنبات.")),
            ],
        )

    assert accepted.refusals == ["leak", "hadith_ineligible", "leak"]
    assert len(accepted.insights) == 1


async def test_a_hadith_waiting_for_its_ruling_with_no_verse_shows_nothing_and_is_dropped(store):
    async with store() as db:
        waiting = await accept(db, scene(), [proposed(quran=None)])
        await rule(db, "bukhari", "1032")
        ruled = await accept(db, scene(), [proposed(quran=None)])

    assert (waiting.insights, waiting.refusals) == ([], ["nothing_to_show"])
    assert len(ruled.insights) == 1


async def test_a_part_or_step_citing_anything_but_its_own_texts_or_a_unit_is_dropped(store):
    def part(text: str, *sources: str) -> ExplanationPart:
        return ExplanationPart(section="value", text=text, sources=list(sources))

    parts = [
        part("آية البصيرة.", "quran:30:50"),
        part("حديثها.", "hadith:bukhari:1032"),
        part("وحدتها.", "masar:T01_06"),
        part("بلا مرجع."),
        part("آية أخرى.", "quran:2:255"),
        part("حديث آخر.", "hadith:muslim:1"),
        part("وحدة لا وجود لها.", "masar:T99_99"),
        part("مذكرة.", "note:rain"),
        part("رمز وحده.", "T01_06"),
        part("نص ضعيف.", "hadith:bukhari:8"),
    ]
    elsewhere = SmallStep(text="تأمّل.", kind="reflection", grounded_in=["quran:2:255"])
    async with store() as db:
        accepted = await accept(
            db,
            scene(),
            [proposed(explanation=parts), proposed(small_step=elsewhere)],
        )

    first, second = accepted.insights
    assert [p.text for p in first.explanation] == [
        "آية البصيرة.",
        "حديثها.",
        "وحدتها.",
        "بلا مرجع.",
    ]
    assert first.small_step is not None
    assert second.small_step is None
    assert accepted.refusals == ["unknown_reference"] * 7


async def test_the_store_overlap_compares_runs_of_seven_folded_words(store):
    verse = verse_text(30, 50)
    async with store() as db:
        assert await overlap.repeats_store(db, [words_of(verse, 0, 7)])
        assert await overlap.repeats_store(db, [words_of(hadith_text("bukhari", 1032), 3, 7)])
        assert not await overlap.repeats_store(db, [words_of(verse, 0, 6)])
        assert not await overlap.repeats_store(db, ["الماء سبب للحياة والمطر نعمة تُرى آثارها هنا"])
        assert not await overlap.repeats_store(db, [])

    assert overlap.patterns(["كتب درس علم شرح نظر سمع بصر قلب"]) == [
        "% درس علم شرح نظر سمع بصر قلب %",
        "% كتب درس علم شرح نظر سمع بصر %",
    ]


async def test_a_chat_answer_that_copies_any_stored_text_is_refused(
    browser, store, flow_settings, model
):
    insight_id = await an_insight(browser, store, flow_settings)
    model.answers.extend([said(answer=f"يقول النص {words_of(verse_text(2, 49), 2, 8)}"), said()])

    refused = await ask(browser, insight_id)

    assert (refused.status_code, refused.json()["error"]) == (502, "CHAT_ANSWER_REJECTED")


NO_VERSE = {"quran_surah": None, "quran_ayah": None, "quran_evidence": None}
NO_HADITH = {"hadith_collection": None, "hadith_number": None, "hadith_evidence": None}


async def an_insight_with(browser, store, flow_settings, **values) -> str:
    owner = await as_guest(browser, store, flow_settings)
    async with store() as db:
        scan = scan_row(owner, status="done")
        db.add(scan)
        await db.flush()
        insight = insight_row(owner, scan_id=scan.id, small_step=None, **values)
        db.add(insight)
        await db.commit()
        return str(insight.id)


@pytest.mark.parametrize(
    ("values", "ruling", "quoted"),
    [
        ({}, None, ("bukhari", 1032)),
        ({}, HadithClassification.DAIF, ("bukhari", 1032)),
        (NO_VERSE, None, ("bukhari", 1032)),
        (NO_HADITH, None, (30, 50)),
    ],
)
async def test_a_chat_answer_quoting_a_cited_text_is_refused_even_while_it_is_hidden(
    browser, store, flow_settings, model, values, ruling, quoted
):
    insight_id = await an_insight_with(browser, store, flow_settings, **values)
    if ruling is not None:
        async with store() as db:
            await rule(db, "bukhari", "1032", ruling)
            await db.commit()
    text = hadith_text(*quoted) if quoted[0] == "bukhari" else verse_text(*quoted)
    # Six words: under the store-wide window, inside the cited texts' shingles.
    model.answers.append(said(answer=f"ورد {words_of(text, 3, 6)}"))

    refused = await ask(browser, insight_id)

    assert (refused.status_code, refused.json()["error"]) == (502, "CHAT_ANSWER_REJECTED")
