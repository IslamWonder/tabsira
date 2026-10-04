"""
A quotation in today's spelling is caught as surely as one in the mushaf's.

Every verse here is read from the store and respelled by `tests.scripture.spelling`:
no verse is typed by hand.
"""

from __future__ import annotations

from itertools import groupby
from random import Random

import pytest
from sqlalchemy import select

from src.models import Hadith, HadithSearch, QuranVerse, QuranVerseSearch
from src.pipeline.leak_guard import ShingleOverlapDetector
from src.scans.accept import accept
from src.scripture import overlap
from src.scripture.guard_fold import guard_fold
from tests.scans.builders import proposed, scene
from tests.scans.test_chat import an_insight, ask, said
from tests.scans.test_scripture_guard import explained
from tests.scripture.spelling import standard, variant

# One verse of each kind the review named: الصلوٰة and الزكوٰة, السمـٰوٰت, رحمت and يحۡيِ.
NAMED = [(2, 43), (3, 190), (30, 50)]


async def stored_verse(db, surah: int, ayah: int) -> str:
    text: str = await db.scalar(
        select(QuranVerse.text).where(QuranVerse.surah == surah, QuranVerse.ayah == ayah)
    )
    return text


async def test_the_store_keeps_the_guard_skeleton_of_every_text(store):
    async with store() as db:
        verses = (
            await db.execute(
                select(QuranVerse.text, QuranVerseSearch.guard_text).join(
                    QuranVerseSearch, QuranVerseSearch.verse_id == QuranVerse.id
                )
            )
        ).all()
        hadiths = (
            await db.execute(
                select(Hadith.text, HadithSearch.guard_text).join(
                    HadithSearch, HadithSearch.hadith_id == Hadith.id
                )
            )
        ).all()

    assert len(verses) >= 20
    assert hadiths
    assert [guard for text, guard in [*verses, *hadiths] if guard != guard_fold(text)] == []


@pytest.mark.parametrize(("surah", "ayah"), NAMED)
async def test_a_verse_in_todays_spelling_is_caught_by_every_guard(store, surah, ayah):
    async with store() as db:
        stored = await stored_verse(db, surah, ayah)
        today = standard(stored)
        in_store = await overlap.repeats_store(db, [today])
        accepted = await accept(db, scene(), [proposed(explanation=explained(f"وفي ذلك {today}"))])

    assert today != stored
    assert in_store
    assert ShingleOverlapDetector([stored]).find(today)
    assert accepted.refusals == ["leak"]


@pytest.mark.parametrize(("surah", "ayah"), NAMED)
async def test_a_chat_answer_in_todays_spelling_is_refused(
    browser, store, flow_settings, model, surah, ayah
):
    insight_id = await an_insight(browser, store, flow_settings)
    async with store() as db:
        today = standard(await stored_verse(db, surah, ayah))
    model.answers.append(said(answer=f"يقول النص {today}"))

    refused = await ask(browser, insight_id)

    assert (refused.status_code, refused.json()["error"]) == (502, "CHAT_ANSWER_REJECTED")


async def test_every_verse_of_the_store_in_any_spelling_is_caught(store):
    async with store() as db:
        rows = (
            await db.execute(
                select(QuranVerse.surah, QuranVerse.ayah, QuranVerse.text).order_by(
                    QuranVerse.surah, QuranVerse.ayah
                )
            )
        ).all()
        # A verse of seven words or more alone; a run of short verses quoted together.
        quotes = [text for _, _, text in rows if len(guard_fold(text).split()) >= overlap.WINDOW]
        for _, verses in groupby(rows, key=lambda row: row.surah):
            quotes.append(" ".join(text for _, _, text in verses))
        rng = Random(46)  # noqa: S311 - a seeded sample, no secret
        spelled = [variant(quote, rng) for quote in quotes for _ in range(3)]
        missed = [text for text in spelled if not await overlap.repeats_store(db, [text])]

    assert len(quotes) >= 10
    assert missed == []
