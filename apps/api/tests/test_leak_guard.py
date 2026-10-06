"""
The leak guard, on synthetic text.

The fixtures have the shape of scripture (marks, introducers, vocalisation) but
are ordinary invented Arabic sentences: no Quran or hadith text is written here.
"""

from __future__ import annotations

import pytest

from src.pipeline.leak_guard import (
    LeakFinding,
    LeakGuard,
    LeakKind,
    LeakVerdict,
    PatternLeakDetector,
    ScriptureLeakError,
    ShingleOverlapDetector,
    arabic_word_count,
    normalize_arabic,
)
from src.scripture.guard_fold import guard_fold

SMALL_HIGH_LIGATURE = chr(0x06D6)
END_OF_AYAH = chr(0x06DD)
ORNATE_OPEN, ORNATE_CLOSE = chr(0xFD3E), chr(0xFD3F)
BASMALA_LIGATURE = chr(0xFDFD)
OPEN_TANWEEN = chr(0x08F0)
FATHA, DAMMA, KASRA, SUKUN, SHADDA = (
    chr(code) for code in (0x064E, 0x064F, 0x0650, 0x0652, 0x0651)
)

SIX_WORDS = "الولد يكتب درسه في البيت الكبير"


def kinds(text: str) -> list[LeakKind]:
    return [finding.kind for finding in PatternLeakDetector().find(text)]


@pytest.mark.parametrize(
    "text",
    [
        "شخص يمسك هاتفًا ويقرأ ما على شاشته، وأمامه كوب قهوة على طاولة خشبية.",
        "قال البائع إن الفاكهة طازجة.",
        "كان النبي ﷺ يحب التيسير على الناس.",
        "انتقال «الولد يكتب درسه في البيت الكبير» من مكان إلى آخر.",
        'قال: "نعم لا"',
        "كما في «الآية المعروضة» وفي «الحديث المعروض».",
        "",
        "A plain English sentence about rain.",
    ],
)
def test_ordinary_text_passes(text):
    assert kinds(text) == []


def test_quranic_annotation_marks_are_refused():
    findings = PatternLeakDetector().find(f"كلمة{SMALL_HIGH_LIGATURE} أخرى{END_OF_AYAH}")

    assert findings == [LeakFinding(kind=LeakKind.QURAN_MARKS, detail="2 characters")]


def test_ornate_brackets_and_quran_signs_are_refused():
    assert kinds(f"{ORNATE_OPEN} كلمات {ORNATE_CLOSE}") == [LeakKind.ORNATE_BRACKETS]
    assert kinds(f"بداية {BASMALA_LIGATURE}") == [LeakKind.QURAN_SIGNS]
    assert kinds(f"كلمة{OPEN_TANWEEN}") == [LeakKind.QURAN_SIGNS]


@pytest.mark.parametrize(
    "introducer",
    [
        "قال تعالى",
        "وقال الله تعالى",
        "يقول الله عز وجل",
        "قوله سبحانه وتعالى",
        "قال رسول الله ﷺ",
        "فقال النبي",
        "صلى الله عليه وسلم",
        "في الحديث الشريف",
        "في الآية الكريمة",
        f"ق{FATHA}ال{FATHA} ت{FATHA}ع{FATHA}ال{FATHA}ى",
    ],
)
def test_a_quotation_after_a_scripture_introducer_is_refused(introducer):
    text = f"{introducer}: «كلمات عربية للاختبار هنا» ثم يتابع الشرح."

    findings = PatternLeakDetector().find(text)

    assert [finding.kind for finding in findings] == [LeakKind.INTRODUCED_QUOTE]
    assert findings[0].detail == "quotation after a scripture introducer: 4 words"


def test_words_after_an_introducer_and_a_colon_are_refused_without_quotes():
    findings = PatternLeakDetector().find(f"قال رسول الله: {SIX_WORDS} للاختبار. ثم شرح.")

    assert findings == [
        LeakFinding(
            kind=LeakKind.INTRODUCED_QUOTE,
            detail="words after a scripture introducer and a colon: 7 words",
        )
    ]


def test_one_word_after_an_introducer_and_a_colon_passes():
    assert kinds("قال تعالى: كذلك. ثم شرح طويل جدًا للمعنى في سياق المشهد.") == []


def test_two_words_after_an_introducer_and_a_colon_are_refused():
    findings = PatternLeakDetector().find("قال تعالى: كلمتان فقط. ثم شرح طويل.")

    assert findings == [
        LeakFinding(
            kind=LeakKind.INTRODUCED_QUOTE,
            detail="words after a scripture introducer and a colon: 2 words",
        )
    ]


@pytest.mark.parametrize("quoted", ["نعم", "نعم لا", "كلمتان فقط"])
def test_any_quotation_after_a_strong_introducer_is_refused(quoted):
    assert kinds(f"قال تعالى «{quoted}» في هذا المشهد.") == [LeakKind.INTRODUCED_QUOTE]
    assert kinds(f"قال رسول الله ﷺ: «{quoted}»") == [LeakKind.INTRODUCED_QUOTE]


def test_the_names_the_chat_gives_the_shown_texts_stay_allowed():
    assert kinds("كما قال تعالى «الآية المعروضة»، وكما في الحديث «الحديث المعروض».") == []


def test_a_long_quotation_after_a_plain_said_is_refused():
    assert kinds(f'قال: "{SIX_WORDS}"') == [LeakKind.INTRODUCED_QUOTE]
    assert kinds(f"وقالت «{SIX_WORDS}»") == [LeakKind.INTRODUCED_QUOTE]
    assert kinds('قال: "الولد يكتب درسه في البيت"') == []


def test_a_very_long_quotation_of_any_arabic_is_refused():
    fifteen = " ".join([SIX_WORDS, SIX_WORDS, "واحد اثنان ثلاثة"])

    assert kinds(f"على اللوحة «{fifteen}»") == [LeakKind.LONG_QUOTE]
    assert kinds(f"على اللوحة «{SIX_WORDS} {SIX_WORDS}»") == []


def vocalised(word: str) -> str:
    """Put a vowel on every letter of an invented word."""
    return "".join(letter + (FATHA, DAMMA, KASRA)[index % 3] for index, letter in enumerate(word))


def test_a_run_of_fully_vocalised_words_is_refused():
    six = " ".join(vocalised(word) for word in SIX_WORDS.split())
    five = " ".join(vocalised(word) for word in SIX_WORDS.split()[:5])

    assert kinds(six) == [LeakKind.VOCALISED_SPAN]
    assert kinds(f"{five} بلا تشكيل {five}") == []
    assert kinds(f"ك{SHADDA}{FATHA}تب{SUKUN} " * 3) == []


def test_normalize_arabic_removes_marks_and_unifies_letters():
    text = f"أَحْمَد{SMALL_HIGH_LIGATURE} إلى المدرسةِ، آخر ـــ مستشفى!"

    assert normalize_arabic(text) == "احمد الي المدرسه اخر مستشفي"
    assert normalize_arabic("Rain, RAIN 2") == "rain rain 2"


def test_arabic_word_count():
    assert arabic_word_count("الولد، يكتب! درسه") == 3
    assert arabic_word_count("no arabic here") == 0


CORPUS = ["الولد يكتب درسه في البيت الكبير كل مساء", "نص آخر لا علاقة له"]


def test_corpus_overlap_finds_a_shared_run_of_words_whatever_the_spelling():
    detector = ShingleOverlapDetector(CORPUS)
    text = f"في الشرح: الوَلَدُ يكتب درسَهُ في البيت{SMALL_HIGH_LIGATURE} ثم ينام."

    assert detector.find(text) == [
        LeakFinding(kind=LeakKind.CORPUS_OVERLAP, detail="1 runs of 5 words found in the corpus")
    ]
    assert detector.find("الولد يكتب درسه في المدرسة") == []
    assert detector.find("كلمتان") == []


def test_corpus_skeletons_are_taken_as_they_are_and_never_folded_again():
    marked = "الوَلَدُ يكتب درسَهُ في البيت"
    skeleton = guard_fold(marked)

    # A text of the corpus is folded once; a skeleton is not folded at all.
    assert ShingleOverlapDetector([marked]).find(marked)
    assert ShingleOverlapDetector(skeletons=[skeleton]).find(marked)
    assert ShingleOverlapDetector(skeletons=[marked]).find(marked) == []
    assert ShingleOverlapDetector().find(marked) == []


def test_the_guard_runs_the_pattern_rules_by_default_and_accepts_more_detectors():
    text = "الولد يكتب درسه في البيت"

    assert LeakGuard().check(text) == LeakVerdict(findings=[])
    assert not LeakGuard().check(text).leaked
    with_corpus = LeakGuard([PatternLeakDetector(), ShingleOverlapDetector(CORPUS)])
    verdict = with_corpus.check(text)
    assert verdict.leaked
    assert verdict.model_dump()["leaked"] is True
    assert LeakGuard([]).check(f"{ORNATE_OPEN}").findings == []


def test_ensure_clean_names_every_refused_field():
    guard = LeakGuard()
    guard.ensure_clean({"description": "مطر على أرض جافة", "evidence": "قطرات على التراب"})

    with pytest.raises(ScriptureLeakError) as caught:
        guard.ensure_clean(
            {
                "description": f"مطر{SMALL_HIGH_LIGATURE}",
                "evidence": "قطرات",
                "question": f"قال تعالى: «{SIX_WORDS}»",
            }
        )

    assert set(caught.value.fields) == {"description", "question"}
    assert str(caught.value) == (
        "scripture-like text in description, question (introduced_quote, quran_marks)"
    )
