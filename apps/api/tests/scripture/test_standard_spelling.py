"""
Our converter of a stored verse into today's spelling, rule by rule (task 05.9).

Every word comes from a stored verse: `standard-spelling-verses.json` holds, for
each rule, a verse copied by a script from the real store and the index of the
word the rule applies to. The expected forms are said with code points, never
typed as scripture.
"""

from __future__ import annotations

import pytest

from src.scripture.guard_fold import guard_fold
from src.scripture.standard_spelling import (
    HA,
    YA,
    standard,
    standard_skeleton,
    standard_word,
    vocative,
)
from src.scripture.text import sha256_hex
from tests.scripture.fixtures import load_json, verse_text

ALEF_HAMZA = chr(0x0623)
WAW_HAMZA = chr(0x0624)
YEH_HAMZA = chr(0x0626)
ALEF_MAQSURA = chr(0x0649)
YEH = chr(0x064A)
TEH = chr(0x062A)
TEH_MARBUTA = chr(0x0629)
WAW = chr(0x0648)
ALEF = chr(0x0627)
SEATS = {WAW_HAMZA, YEH_HAMZA}


def word(case: str) -> str:
    data = load_json("standard-spelling-verses.json")
    found = data["cases"][case]
    verse = next(
        v for v in data["verses"] if (v["surah"], v["ayah"]) == (found["surah"], found["ayah"])
    )
    return str(verse["text"]).split()[found["word"]]


def test_the_fixture_verses_are_stored_texts_with_their_hashes():
    verses = load_json("standard-spelling-verses.json")["verses"]

    assert verses
    assert [v for v in verses if sha256_hex(v["text"]) != v["text_sha256"]] == []


@pytest.mark.parametrize(
    ("case", "seat"),
    [
        ("line_hamza_kasra", YEH_HAMZA),
        ("line_hamza_damma", WAW_HAMZA),
        ("tooth_kasra", YEH_HAMZA),
        ("tooth_damma", WAW_HAMZA),
    ],
)
def test_a_hamza_takes_the_seat_its_vowels_give_it_today(case, seat):
    written = standard_word(word(case))

    assert seat in written
    assert (SEATS - {seat}) & set(written) == set()


@pytest.mark.parametrize("case", ["tooth_unseated", "tooth_before_alef"])
def test_a_hamza_after_a_fatha_or_before_an_alef_takes_no_seat(case):
    assert SEATS & set(standard_word(word(case))) == set()


def test_a_final_hamza_on_a_waw_before_a_silent_alef_is_on_an_alef_today():
    assert standard_word(word("final_waw_hamza")).endswith(ALEF_HAMZA)


def test_a_final_hamza_and_alef_after_a_fatha_is_written_with_an_alef_maqsura():
    assert standard_word(word("final_hamza_alef")).endswith(ALEF_HAMZA + ALEF_MAQSURA)


def test_the_vocative_and_the_particle_of_attention_are_written_apart():
    called = standard(word("vocative")).split()
    after_waw = standard(word("vocative_after_waw")).split()
    attention = standard(word("attention")).split()

    assert (len(called), called[0]) == (2, YA)
    assert (len(after_waw), after_waw[0]) == (2, WAW + YA)
    assert (len(attention), attention[0]) == (2, HA)
    assert attention[1].startswith(ALEF_HAMZA)
    assert vocative(word("attention")) is None
    split = vocative(word("vocative"))
    assert split is not None
    assert split[0] == YA
    assert word("vocative").endswith(split[1])


def test_a_writer_may_choose_otherwise_than_the_standard():
    that = verse_text(2, 2).split()[0]
    mercy = verse_text(30, 50).split()[3]
    on = verse_text(30, 50).split()[15]

    # «ذلك» without its alef by default, with it when asked.
    assert ALEF not in standard_word(that)
    assert ALEF in standard_word(that, keep_alef=True)
    # The mushaf's open teh of «رحمت» is a teh marbuta today, unless kept.
    assert standard_word(mercy).endswith(TEH_MARBUTA)
    assert standard_word(mercy, open_teh=False).endswith(TEH)
    assert standard_word(mercy, open_teh=True).endswith(TEH_MARBUTA)
    # A final yeh may be doubled; a word that ends otherwise is left alone.
    assert standard_word(on, long_yeh=True) == standard_word(on)
    assert standard_word(standard_word(on) + YEH, long_yeh=True).endswith(YEH + YEH)


def test_the_skeleton_is_the_guard_fold_of_todays_spelling():
    text = verse_text(30, 50)

    assert standard_skeleton(text) == guard_fold(standard(text))
