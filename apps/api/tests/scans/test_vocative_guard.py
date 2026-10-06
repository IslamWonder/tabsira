"""
A verse written as today writes it is caught, the vocative apart (task 05.9).

The mushaf joins «يا» to the next word; today's spelling writes it apart, so the
fold of the Uthmani text alone missed 18 of the 20 short verses with a joined
vocative. The guard now also compares with each verse converted into today's
spelling by `src.scripture.standard_spelling`, kept as a skeleton only. Every
verse here is read from the store (copied from the real store into
`vocative-verses.json`) and respelled from it: no verse is typed by hand.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from random import Random

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, func, select, update

from src.database import get_db
from src.models import (
    QuranVerse,
    QuranVerseSearch,
    QuranVerseStandardGuard,
    ScanEvent,
    ScanStatus,
)
from src.models.scripture import quran_verse_standard_spans
from src.pipeline.engine import EngineResult, EngineStatus
from src.pipeline.insight.guard import quran_detector, scripture_guard
from src.pipeline.leak_guard import SHINGLE_WORDS, ShingleOverlapDetector, _shingles
from src.scans.accept import accept, cited_texts
from src.scans.workflow import run_scan
from src.scripture import overlap
from src.scripture.guard_fold import guard_fold
from src.scripture.quran import refresh_standard_guard, refresh_verse_spans
from src.scripture.standard_spelling import standard_skeleton
from src.scripture.text import sha256_hex
from tests.helpers import client_for
from tests.scans.builders import proposed, quran, scene
from tests.scans.conftest import store_extra
from tests.scans.test_chat import an_insight, ask, said
from tests.scans.test_scripture_guard import explained
from tests.scans.test_workflow import (
    StaticEngine,
    http,
    new_scan,
    scene_answer,
    services_for,
    the_scan,
)
from tests.scripture.spelling import standard, variant

__all__ = ["http"]

# The verses of three to six words with a joined vocative that the Uthmani skeleton alone
# let through when written apart (docs/plans/05_insight_engine.md, task 05.9).
ESCAPED = [
    (20, 11),
    (20, 17),
    (20, 19),
    (20, 36),
    (20, 49),
    (20, 83),
    (20, 95),
    (21, 14),
    (21, 62),
    (25, 28),
    (27, 9),
    (37, 20),
    (37, 104),
    (68, 31),
    (69, 27),
    (71, 2),
    (89, 24),
    (109, 1),
]
# The two others of the twenty: caught before too, by the span with the verses after them.
CAUGHT_BEFORE = [(82, 6), (89, 27)]
IDS = [f"{surah}:{ayah}" for surah, ayah in ESCAPED]
ALL = [*ESCAPED, *CAUGHT_BEFORE]
ALL_IDS = [f"{surah}:{ayah}" for surah, ayah in ALL]
# Verses of the fixture with seven words or more in today's spelling: five of their words
# are a part of the verse, never the whole of it.
LONGER = [(21, 62), (25, 28), (27, 9), (71, 2), (82, 6)]
LONGER_IDS = [f"{surah}:{ayah}" for surah, ayah in LONGER]


@pytest_asyncio.fixture
async def vocatives(store):
    """The scan store with the twenty verses, imported with their derived skeletons."""
    async with store() as db:
        await store_extra(db, "vocative-verses.json")
        await db.commit()
    return store


async def stored_verse(db, surah: int, ayah: int) -> QuranVerse:
    return (
        await db.scalars(
            select(QuranVerse).where(QuranVerse.surah == surah, QuranVerse.ayah == ayah)
        )
    ).one()


async def today(store, surah: int, ayah: int) -> str:
    """The stored verse in today's spelling, the vocative written apart."""
    async with store() as db:
        return standard((await stored_verse(db, surah, ayah)).text)


@pytest.mark.parametrize(("surah", "ayah"), ALL, ids=ALL_IDS)
async def test_the_store_keeps_the_skeleton_of_each_verse_in_todays_spelling(
    vocatives, surah, ayah
):
    async with vocatives() as db:
        verse = await stored_verse(db, surah, ayah)
        kept = await db.get_one(QuranVerseStandardGuard, verse.id)
    written = standard(verse.text)

    # The fold of the mushaf's text cannot reach today's word boundaries; the kept one does.
    assert guard_fold(written) != guard_fold(verse.text)
    assert kept.guard_text == guard_fold(written) == standard_skeleton(verse.text)
    assert kept.guard_words == len(kept.guard_text.split())


@pytest.mark.parametrize(("surah", "ayah"), ALL, ids=ALL_IDS)
async def test_a_short_verse_written_as_today_is_refused_by_the_store_check(vocatives, surah, ayah):
    written = await today(vocatives, surah, ayah)
    async with vocatives() as db:
        stored = (await stored_verse(db, surah, ayah)).text
        assert await overlap.repeats_store(db, [written])
        assert await overlap.repeats_store(db, [f"ونتذكر هنا {written} في كل حال"])
        for seed in range(3):
            spelled = variant(stored, Random(seed))  # noqa: S311 - a seeded sample, no secret
            assert await overlap.repeats_store(db, [spelled]), (surah, ayah, seed)


async def test_without_the_derived_skeletons_the_eighteen_escape_and_the_two_others_do_not(
    vocatives,
):
    async with vocatives() as db:
        await db.execute(delete(QuranVerseStandardGuard))
        await refresh_verse_spans(db)
        texts = {ref: standard((await stored_verse(db, *ref)).text) for ref in ALL}
        escaped = [ref for ref in ESCAPED if not await overlap.repeats_store(db, [texts[ref]])]
        caught = [ref for ref in CAUGHT_BEFORE if await overlap.repeats_store(db, [texts[ref]])]

    assert (escaped, caught) == (ESCAPED, CAUGHT_BEFORE)


async def test_missing_or_stale_skeletons_are_written_again_and_current_ones_left_alone(
    vocatives,
):
    async with vocatives() as db:
        verses = await db.scalar(select(func.count()).select_from(QuranVerse))
        current = await refresh_standard_guard(db)
        first = await db.scalar(select(func.min(QuranVerse.id)))
        await db.execute(
            delete(QuranVerseStandardGuard).where(QuranVerseStandardGuard.verse_id == first)
        )
        # As if the converter or the fold had changed since these were written.
        await db.execute(
            update(QuranVerseStandardGuard)
            .where(QuranVerseStandardGuard.verse_id != first)
            .values(guard_text="x")
        )
        rewritten = await refresh_standard_guard(db)
        rows = (
            await db.execute(
                select(QuranVerse.text, QuranVerseStandardGuard.guard_text).join(
                    QuranVerseStandardGuard, QuranVerseStandardGuard.verse_id == QuranVerse.id
                )
            )
        ).all()
        spans = set(await db.scalars(select(quran_verse_standard_spans.c.guard_text)))

    assert (current, rewritten) == (0, verses)
    assert len(rows) == verses
    assert [text for text, kept in rows if kept != standard_skeleton(text)] == []
    assert "x" not in spans


@pytest.mark.parametrize(("surah", "ayah"), ESCAPED, ids=IDS)
async def test_an_insight_quoting_a_short_verse_as_today_is_refused(vocatives, surah, ayah):
    written = await today(vocatives, surah, ayah)
    async with vocatives() as db:
        accepted = await accept(
            db, scene(), [proposed(explanation=explained(f"وفي ذلك {written}."))]
        )

    assert accepted.refusals == ["leak"]


@pytest.mark.parametrize(("surah", "ayah"), ESCAPED, ids=IDS)
async def test_a_chat_answer_quoting_a_short_verse_as_today_is_refused(
    browser, vocatives, flow_settings, model, surah, ayah
):
    insight_id = await an_insight(browser, vocatives, flow_settings)
    model.answers.append(said(answer=f"يقول النص {await today(vocatives, surah, ayah)}"))

    refused = await ask(browser, insight_id)

    assert (refused.status_code, refused.json()["error"]) == (502, "CHAT_ANSWER_REJECTED")


@pytest.mark.parametrize(("surah", "ayah"), ESCAPED, ids=IDS)
async def test_a_scene_describing_a_short_verse_as_today_fails_the_scan(
    vocatives, redis, http, flow_settings, surah, ayah
):
    written = await today(vocatives, surah, ayah)
    scan_id = await new_scan(vocatives, redis)
    services, _ = services_for(
        vocatives,
        redis,
        http,
        flow_settings,
        StaticEngine(EngineResult(status=EngineStatus.OK)),
        answers=[scene_answer(description=f"نبتة {written}")],
    )

    await run_scan(services, scan_id, 1)

    scan = await the_scan(vocatives, scan_id)
    async with vocatives() as db:
        stages = (await db.scalars(select(ScanEvent).where(ScanEvent.scan_id == scan_id))).all()
    assert (scan.status, scan.error_code) == (ScanStatus.FAILED, "VISION_FAILED")
    assert ("understand", "failed", "leak") in {(e.stage, e.status, e.code) for e in stages}


def five_words_today(stored: str) -> str:
    """Five words of the verse in today's spelling whose run the mushaf's skeleton lacks."""
    mushaf = set(_shingles(guard_fold(stored), SHINGLE_WORDS))
    words = standard(stored).split()
    for start in range(len(words) - SHINGLE_WORDS + 1):
        run = " ".join(words[start : start + SHINGLE_WORDS])
        folded = tuple(guard_fold(run).split())
        if len(folded) == SHINGLE_WORDS and folded not in mushaf:
            return run
    raise AssertionError(stored)


async def five_words(store, surah: int, ayah: int) -> tuple[str, str]:
    async with store() as db:
        stored = (await stored_verse(db, surah, ayah)).text
    return stored, five_words_today(stored)


@pytest.mark.parametrize(("surah", "ayah"), LONGER, ids=LONGER_IDS)
async def test_five_words_in_todays_spelling_escape_every_check_of_the_mushafs_text_alone(
    vocatives, surah, ayah
):
    stored, run = await five_words(vocatives, surah, ayah)
    async with vocatives() as db:
        in_store = await overlap.repeats_store(db, [run])
        mushaf = ShingleOverlapDetector(await db.scalars(select(QuranVerseSearch.guard_text)))

    # Under the store's seven-word window and no verse whole: only the five-word checks see it.
    assert not in_store
    assert ShingleOverlapDetector([stored]).find(run) == []
    assert mushaf.find(run) == []


@pytest.mark.parametrize(("surah", "ayah"), LONGER, ids=LONGER_IDS)
async def test_the_insight_stages_refuse_five_words_of_any_verse_in_todays_spelling(
    vocatives, surah, ayah
):
    _, run = await five_words(vocatives, surah, ayah)
    async with vocatives() as db:
        detector = await quran_detector(db)
        refused = await scripture_guard(detector, session=db).leaks([f"وفي ذلك {run}"])

    assert detector.find(run)
    assert refused


@pytest.mark.parametrize(("surah", "ayah"), LONGER, ids=LONGER_IDS)
async def test_an_insight_quoting_five_words_of_its_verse_as_today_is_refused(
    vocatives, surah, ayah
):
    _, run = await five_words(vocatives, surah, ayah)
    async with vocatives() as db:
        accepted = await accept(
            db,
            scene(),
            [proposed(quran=quran(surah, ayah), explanation=explained(f"وفي ذلك {run}."))],
        )

    assert accepted.refusals == ["leak"]


@pytest.mark.parametrize(("surah", "ayah"), LONGER, ids=LONGER_IDS)
async def test_a_chat_answer_quoting_five_words_of_its_verse_as_today_is_refused(
    browser, vocatives, flow_settings, model, surah, ayah
):
    _, run = await five_words(vocatives, surah, ayah)
    insight_id = await an_insight(
        browser, vocatives, flow_settings, quran_surah=surah, quran_ayah=ayah
    )
    model.answers.append(said(answer=f"يقول النص {run}"))

    refused = await ask(browser, insight_id)

    assert (refused.status_code, refused.json()["error"]) == (502, "CHAT_ANSWER_REJECTED")


async def test_the_cited_texts_hold_the_verse_and_its_skeleton_in_todays_spelling(vocatives):
    async with vocatives() as db:
        stored = (await stored_verse(db, 71, 2)).text
        cited = await cited_texts(db, (71, 2), None)

    assert cited == [stored, standard_skeleton(stored)]


@pytest_asyncio.fixture
async def api(app, vocatives) -> AsyncIterator[AsyncClient]:
    """A client of the read API over the store with the derived skeletons."""
    async with vocatives() as db:

        async def session_override() -> AsyncIterator:
            yield db

        app.dependency_overrides[get_db] = session_override
        try:
            async with client_for(app) as client:
                yield client
        finally:
            app.dependency_overrides.pop(get_db)


@pytest.mark.parametrize(("surah", "ayah"), ALL, ids=ALL_IDS)
async def test_the_displayed_verse_stays_the_stored_uthmani_text_with_its_hash(
    api, vocatives, surah, ayah
):
    async with vocatives() as db:
        verse = await stored_verse(db, surah, ayah)
        kept = await db.get_one(QuranVerseStandardGuard, verse.id)

    body = (await api.get(f"/scripture/quran/{surah}/{ayah}")).json()

    assert body["text"] == verse.text
    assert body["sha256"] == sha256_hex(body["text"]) == verse.text_sha256
    # The derived copy is a skeleton only, kept apart, and never served.
    assert set(QuranVerseStandardGuard.__table__.columns.keys()) == {
        "verse_id",
        "guard_text",
        "guard_words",
    }
    assert kept.guard_text not in str(body)
    assert standard(verse.text) not in str(body)
