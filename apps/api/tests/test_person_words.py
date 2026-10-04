"""
No inference of religion, age or gender from a photo (v2 §0.6, §6): the server's word guard.

Every word of the list is tried in each form the model may write it (bare, with the article, a
conjunction or a preposition, with harakat, inside punctuation), and the words the spec allows
(objects, symbols, «شخص» itself) are shown to pass untouched.
"""

from __future__ import annotations

import pytest

from src.pipeline.person_words import (
    ARABIC,
    ENGLISH,
    PERSON,
    PERSON_EN,
    PERSONS,
    PERSONS_EN,
    Neutralised,
    neutralise_arabic,
    neutralise_arabic_label,
    neutralise_english_label,
)

ALLOWED_ARABIC = ["شخص", "أشخاص", "حجاب", "سجادة", "مسجد", "مصحف", "يد", "قطة", "هاتف", "شخصان"]
ALLOWED_ENGLISH = ["person", "people", "smartphone", "prayer rug", "mosque", "mankind", "manual"]


@pytest.mark.parametrize(("word", "neutral"), sorted(ARABIC.items()))
def test_every_arabic_descriptor_becomes_the_neutral_word_in_a_sentence(word, neutral):
    result = neutralise_arabic(f"{word} يمسك هاتفًا")

    assert result == Neutralised(f"{neutral} يمسك هاتفًا", (word,))
    assert result.changed


@pytest.mark.parametrize(
    "prefix", ["ال", "و", "وال", "ب", "بال", "ل", "لل", "ك", "كال", "ف", "فال"]
)
def test_the_article_a_conjunction_or_a_preposition_is_kept_in_front_of_the_neutral_word(prefix):
    result = neutralise_arabic(f"{prefix}رجل")

    assert result.text == f"{prefix}{PERSON}"
    assert result.replaced == (f"{prefix}رجل",)


def test_harakat_and_punctuation_around_a_descriptor_do_not_hide_it():
    result = neutralise_arabic("«رَجُلٌ عَجُوزٌ»، يجلس بجانب طفلةٍ.")

    assert result.text == "«شخص شخص»، يجلس بجانب شخص."
    assert result.replaced == ("رجل", "عجوز", "طفلة")


def test_the_definite_form_of_a_woman_is_found_too():
    assert neutralise_arabic("المرأة والرجلان").text == "الشخص والشخصان"


@pytest.mark.parametrize("text", ALLOWED_ARABIC)
def test_objects_symbols_and_the_neutral_word_itself_pass_untouched(text):
    sentence = f"{text} على الطاولة"

    assert neutralise_arabic(sentence) == Neutralised(sentence, ())


def test_an_empty_or_whitespace_text_is_returned_as_it_is():
    assert neutralise_arabic("") == Neutralised("", ())
    assert neutralise_arabic("   ") == Neutralised("   ", ())


def test_an_arabic_label_becomes_the_whole_neutral_word():
    assert neutralise_arabic_label("فتاة صغيرة") == Neutralised(PERSON, ("فتاة",))
    assert neutralise_arabic_label("ثلاث نساء") == Neutralised(PERSONS, ("نساء",))
    assert neutralise_arabic_label("رجلان") == Neutralised(PERSONS, ("رجلان",))
    assert neutralise_arabic_label("هاتف ذكي") == Neutralised("هاتف ذكي", ())


@pytest.mark.parametrize(("word", "neutral"), sorted(ENGLISH.items()))
def test_every_english_descriptor_turns_the_label_into_person_or_people(word, neutral):
    assert neutralise_english_label(f"{word} with a cup") == Neutralised(neutral, (word,))


def test_a_label_with_several_descriptors_is_plural_when_any_of_them_is():
    assert neutralise_english_label("Old Man") == Neutralised(PERSON_EN, ("old", "man"))
    assert neutralise_english_label("elderly women") == Neutralised(
        PERSONS_EN, ("elderly", "women")
    )


@pytest.mark.parametrize("label", ALLOWED_ENGLISH)
def test_english_labels_that_name_no_descriptor_pass_untouched(label):
    assert neutralise_english_label(label) == Neutralised(label, ())


def test_the_list_covers_the_words_the_prompt_forbids():
    forbidden_arabic = [
        "طفل",
        "طفلة",
        "ولد",
        "بنت",
        "فتاة",
        "صبي",
        "رجل",
        "امرأة",
        "سيدة",
        "شاب",
        "شابة",
        "مسن",
        "عجوز",
    ]
    forbidden_english = ["child", "kid", "boy", "girl", "man", "woman", "lady", "old"]

    assert set(forbidden_arabic) <= set(ARABIC)
    assert set(forbidden_english) <= set(ENGLISH)
    assert {"مسلم", "مسلمة", "محجبة"} <= set(ARABIC)
