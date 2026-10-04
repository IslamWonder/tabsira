"""The guard fold: a stored verse and the same verse in today's spelling fold alike."""

from __future__ import annotations

from random import Random

import pytest

from src.scripture.guard_fold import guard_fold
from src.scripture.text import search_copy
from tests.scripture.fixtures import load_json
from tests.scripture.spelling import standard, variant


def fixture_verses() -> list[tuple[int, int, str]]:
    return [
        (surah["id"], ayah["number"], ayah["text"])
        for surah in load_json("quranpedia-mushafs-2.json")["data"]["surahs"]
        for ayah in surah["ayahs"]
    ]


def test_every_fixture_verse_in_todays_spelling_folds_to_its_stored_skeleton():
    for surah, ayah, stored in fixture_verses():
        assert guard_fold(standard(stored)) == guard_fold(stored), (surah, ayah)
        for seed in range(5):
            spelled = variant(stored, Random(seed))  # noqa: S311 - a seeded sample, no secret
            assert guard_fold(spelled) == guard_fold(stored), (surah, ayah, seed)


def test_the_search_fold_keeps_the_uthmani_forms_for_retrieval():
    apart = [
        (surah, ayah)
        for surah, ayah, stored in fixture_verses()
        if search_copy(standard(stored)) != search_copy(stored)
    ]

    # Why the guard needs a fold of its own: most verses differ under the search fold.
    assert (30, 50) in apart
    assert (112, 1) not in apart


@pytest.mark.parametrize(
    ("one", "other"),
    [
        ("الصلوة", "الصلاة"),
        ("الزكوة", "الزكاة"),
        ("الحيوة", "الحياة"),
        ("يحي", "يحيي"),
        ("اليل", "الليل"),
        ("رحمت", "رحمة"),
        ("مسول", "مسؤول"),
        ("الي", "إلى"),
        ("السموت", "السماوات"),
    ],
)
def test_the_two_spellings_of_a_word_fold_alike(one, other):
    assert guard_fold(one) == guard_fold(other)


def test_different_words_stay_different():
    words = ["كتب", "قلم", "ماء", "نور", "أرض", "شمس"]

    assert len({guard_fold(word) for word in words}) == len(words)
    assert guard_fold("") == ""
