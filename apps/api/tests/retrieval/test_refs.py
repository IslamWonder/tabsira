from __future__ import annotations

import pytest
from sqlalchemy import select

from src.models import Hadith, QuranVerse
from src.retrieval.refs import (
    BadReferenceError,
    HadithKey,
    Numbering,
    VerseRange,
    hadith_key,
    is_quran,
    parse_hadith,
    parse_quran,
    quran_key,
    resolve_hadiths,
    resolve_verses,
)


def test_quran_keys_name_a_verse_a_run_or_a_surah():
    assert parse_quran("Q:30:50") == VerseRange(30, 50, 50)
    assert parse_quran(" Q:3:190-191 ") == VerseRange(3, 190, 191)
    assert parse_quran("Q:112") == VerseRange(112, 1, None)
    assert VerseRange(112, 1, None).contains(112, 4)
    assert not VerseRange(3, 190, 191).contains(3, 192)
    assert not VerseRange(3, 190, 191).contains(4, 190)


@pytest.mark.parametrize("key", ["Q:30:", "30:50", "Q:a:1", "H:bukhari:1"])
def test_a_key_that_is_not_a_quran_reference_is_refused(key):
    with pytest.raises(BadReferenceError, match="not a Quran reference"):
        parse_quran(key)


def test_hadith_keys_carry_the_book_the_number_and_a_narration_letter():
    assert parse_hadith("H:bukhari:1032") == HadithKey("bukhari", "1032")
    assert parse_hadith("H:bukhari:402.2") == HadithKey("bukhari", "402.2")
    assert parse_hadith("H:muslim:8a") == HadithKey("muslim", "8", "a")
    with pytest.raises(BadReferenceError, match="not a hadith reference"):
        parse_hadith("H:Bukhari:1")


def test_keys_are_written_back_the_same_way():
    assert quran_key(30, 50) == "Q:30:50"
    assert hadith_key("bukhari", "1032") == "H:bukhari:1032"
    assert is_quran("Q:1:1")
    assert not is_quran("H:bukhari:1")


async def test_quran_keys_resolve_to_the_stored_verses_they_cover(world):
    ids = {
        surah * 1000 + ayah: verse_id
        for verse_id, surah, ayah in (
            await world.execute(select(QuranVerse.id, QuranVerse.surah, QuranVerse.ayah))
        ).all()
    }

    found = await resolve_verses(world, ["Q:30:50", "Q:112", "Q:2:1-2", "Q:99:1"])

    assert found["Q:30:50"] == [ids[30050]]
    assert found["Q:112"] == [ids[112001], ids[112002], ids[112003], ids[112004]]
    assert found["Q:2:1-2"] == [ids[2001], ids[2002]]
    assert found["Q:99:1"] == []
    assert await resolve_verses(world, []) == {}


async def test_hadith_keys_resolve_by_stored_number_or_by_sunnah_com_numbering(world):
    ids = {
        f"{collection}:{number}": hadith_id
        for hadith_id, collection, number in (
            await world.execute(select(Hadith.id, Hadith.collection, Hadith.number))
        ).all()
    }

    stored = await resolve_hadiths(world, ["H:bukhari:1032", "H:muslim:113", "H:muslim:9999"])
    anchors = await resolve_hadiths(
        world, ["H:muslim:16c", "H:muslim:16", "H:bukhari:8"], Numbering.SUNNAH_COM
    )

    assert stored == {
        "H:bukhari:1032": [ids["bukhari:1032"]],
        "H:muslim:113": [ids["muslim:113"]],
        "H:muslim:9999": [],
    }
    # Muslim 16c of sunnah.com is the third narration of Abd al-Baqi's 16: stored as 113.
    assert anchors["H:muslim:16c"] == [ids["muslim:113"]]
    assert anchors["H:muslim:16"] == []
    assert anchors["H:bukhari:8"] == [ids["bukhari:8"]]
    assert await resolve_hadiths(world, ["H:muslim:16c"], Numbering.SUNNAH_COM) == {
        "H:muslim:16c": [ids["muslim:113"]]
    }
    assert await resolve_hadiths(world, []) == {}
