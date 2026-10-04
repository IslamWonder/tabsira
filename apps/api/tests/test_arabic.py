from __future__ import annotations

import pytest

from src import arabic
from src.arabic import (
    bare_form,
    contains_arabic,
    normalize_arabic,
    search_variants,
    split_list,
    strip_article,
    tokens,
)


@pytest.mark.parametrize(
    ("written", "search_form"),
    [
        # Tashkeel and the dagger alef are marks, not letters.
        ("بَرَد", "برد"),
        ("الرَّحْمَٰن", "الرحمن"),
        # Every alef carrier is one letter; so are the two yehs and the teh marbuta.
        ("أرض إبل آية ٱسم", "ارض ابل ايه اسم"),
        ("مستشفى", "مستشفي"),
        ("شجرة", "شجره"),
        ("مسؤول رئيس شيء", "مسوول رييس شيء"),
        # Tatweel only stretches a word.
        ("شـــمس", "شمس"),
        # Persian letters typed on an Arabic keyboard.
        ("کتاب فارسی", "كتاب فارسي"),
        # Digits: Arabic-Indic and Persian become ASCII.
        ("سورة ١٢٣ و ۴۵", "سوره 123 و 45"),
        # Punctuation of both scripts and runs of spaces are one space.
        ("  سماء،  أفق؛ شمس.  ", "سماء افق شمس"),
        ("«ماء» (عذب)", "ماء عذب"),
        # Presentation forms fold to the base letters.
        ("\N{ARABIC LIGATURE LAM WITH ALEF ISOLATED FORM}", "لا"),
        # Invisible direction marks left behind by a copy from a web page.
        ("\N{RIGHT-TO-LEFT MARK}ماء\N{LEFT-TO-RIGHT MARK}\N{RIGHT-TO-LEFT EMBEDDING}", "ماء"),
        # Latin letters are lower-cased: detector labels are English.
        ("Cell Phone", "cell phone"),
        ("", ""),
        ("،؛ .", ""),
    ],
)
def test_normalize_gives_the_search_form(written, search_form):
    assert normalize_arabic(written) == search_form


def test_normalizing_twice_changes_nothing():
    text = "الرَّحْمَٰنُ، أَرْضٌ ١٢ Cell-Phone"

    once = normalize_arabic(text)

    assert normalize_arabic(once) == once


def test_the_article_is_removed_only_when_a_stem_remains():
    assert strip_article("السماء") == "سماء"
    assert strip_article("ال") == "ال"
    assert strip_article("الي") == "الي"
    assert strip_article("الله") == "له"
    assert strip_article("سماء") == "سماء"
    # Particles fused to the article are left alone: «والدين» is parents, not religion.
    assert strip_article("والدين") == "والدين"
    assert arabic.ARTICLE == "ال"


def test_the_bare_form_drops_the_article_of_every_word():
    assert bare_form("الطَّائِرَةُ الكبيرة") == "طايره كبيره"
    assert bare_form("سماء") == "سماء"
    assert bare_form("ال") == "ال"
    assert bare_form("") == ""


def test_tokens_are_the_words_in_search_form():
    assert tokens("الأطفالُ يلعبون، في الحديقة") == ["الاطفال", "يلعبون", "في", "الحديقه"]
    assert tokens("  ") == []


def test_variants_cover_the_article_on_either_side():
    # The vision model says «السماء»; the ontology keeps «سماء».
    assert search_variants("السماء") == ["السماء", "سماء"]
    # The ontology keeps «الكعبة» (with its article); a detector says «كعبة».
    assert search_variants("كعبة") == ["كعبه", "الكعبه"]
    # Every word loses its article; the first one gets it back in the third form.
    assert search_variants("المياه الجارية") == ["المياه الجاريه", "مياه جاريه", "المياه جاريه"]
    assert search_variants("") == []
    assert search_variants("، ") == []


def test_variants_have_no_duplicates_and_never_stack_the_article():
    assert search_variants("الكعبة") == ["الكعبه", "كعبه"]
    # The article cannot be removed from a two-letter stem, and is not added twice.
    assert search_variants("الا") == ["الا"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [("ماء", True), ("water", False), ("cell phone ١٢٣", False), ("pen قلم", True), ("", False)],
)
def test_contains_arabic_looks_for_letters_only(text, expected):
    assert contains_arabic(text) is expected


def test_a_list_cell_is_split_on_the_arabic_comma_and_its_neighbours():
    assert split_list("سماء، أفق، شمس") == ["سماء", "أفق", "شمس"]
    assert split_list("سماء, أفق ؛ شمس;قمر\nنجوم") == ["سماء", "أفق", "شمس", "قمر", "نجوم"]
    # Items are trimmed, empty ones dropped, the words themselves untouched.
    assert split_list(" بَرَد ،، ،  ") == ["بَرَد"]
    assert split_list("") == []
    # A slash or a bar inside an item is part of the item.
    assert split_list("مياه/ري، ماء|جار") == ["مياه/ري", "ماء|جار"]
