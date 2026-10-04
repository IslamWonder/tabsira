"""Hadith display spans: positions in the stored text that always join back to it exactly."""

from __future__ import annotations

from itertools import pairwise

from hypothesis import given, settings
from hypothesis import strategies as st

from src.scripture.hadith import parse_open_hadith_csv
from src.scripture.spans import Span, SpanRole, hadith_spans
from src.scripture.text import search_copy
from tests.scripture.fixtures import fixture_path, hadith_text, load_json

RLM = chr(0x200F)
# Words and marks that steer the cut: transmission words, markers, quotes, braces.
TOKENS = [
    " ",
    "، ",
    ": ",
    RLM,
    '"',
    "«",
    "»",
    "“",
    "”",
    "{",
    "}",
    "حَدَّثَنَا",
    "أَخْبَرَنَا",
    "عَنْ",
    "قَالَ",
    "أَنَّ",
    "سَمِعْتُ",
    "رَسُولَ",
    "اللَّهِ",
    "النَّبِيِّ",
    "صلى الله عليه وسلم",
    "فُلَانٍ",
    "خَيْرٌ",
]
texts = st.one_of(
    st.text(),
    st.lists(st.sampled_from(TOKENS), max_size=40).map("".join),
    st.lists(st.sampled_from([*TOKENS, " "]), max_size=40).map(" ".join),
)


def _check(text: str, spans: list[Span]) -> None:
    assert "".join(text[span.start : span.end] for span in spans) == text
    assert spans[0].start == 0
    assert spans[-1].end == len(text)
    for before, after in pairwise(spans):
        assert before.end == after.start
    if text:
        assert all(span.start < span.end for span in spans)
    roles = [span.role for span in spans]
    assert len(roles) == len(set(roles))
    order = [SpanRole.CHAIN, SpanRole.BODY, SpanRole.WORDS, SpanRole.TAIL]
    assert roles == sorted(roles, key=order.index)
    assert SpanRole.BODY in roles


@settings(max_examples=500, deadline=None)
@given(texts)
def test_the_slices_always_join_back_into_the_stored_text(text):
    _check(text, hadith_spans(text))


def test_every_fixture_hadith_is_covered_exactly():
    texts_ = [
        hadith["text"]
        for book in ("bukhari", "muslim", "abudawud")
        for hadith in load_json(f"ara-{book}.json")["hadiths"]
    ]
    texts_ += [
        record.text
        for name in ("musnad-ahmad.csv", "sunan-al-darimi.csv")
        for record in parse_open_hadith_csv(fixture_path(name).read_bytes()).records
    ]

    for text in texts_:
        _check(text, hadith_spans(text))


def test_a_hadith_with_a_chain_and_one_quotation_gets_four_spans():
    text = hadith_text("bukhari", 1032)

    spans = hadith_spans(text)

    assert [span.role for span in spans] == ["chain", "body", "words", "tail"]
    chain, body, words, tail = (text[span.start : span.end] for span in spans)
    assert search_copy(body).startswith("ان رسول الله")
    assert chain.startswith(text[:10])
    assert words.startswith('"')
    assert words.rstrip(RLM).endswith('"')
    assert tail.strip()


def test_an_unclosed_quotation_runs_to_the_end():
    text = hadith_text("bukhari", 1)

    spans = hadith_spans(text)

    assert text.count('"') == 1
    assert [span.role for span in spans] == ["chain", "body", "words"]
    assert spans[-1].end == len(text)


def test_punctuation_after_the_quotation_stays_with_the_words():
    text = 'حَدَّثَنَا فُلَانٍ عَنْ النَّبِيِّ قَالَ "خَيْرٌ".' + RLM

    spans = hadith_spans(text)

    assert [span.role for span in spans] == ["chain", "body", "words"]


def test_a_chain_without_any_quotation_is_cut_before_the_body():
    text = "حَدَّثَنَا فُلَانٍ عَنْ فُلَانٍ أَنَّ رَسُولَ اللَّهِ قَالَ خَيْرٌ"

    spans = hadith_spans(text)

    assert [span.role for span in spans] == ["chain", "body"]
    assert text[spans[1].start :].startswith("أَنَّ")


def test_doubt_keeps_one_body_span():
    dialogue = 'حَدَّثَنَا فُلَانٍ أَنَّ النَّبِيِّ قَالَ "خَيْرٌ" قَالَ "خَيْرٌ"'
    no_marker = "حَدَّثَنَا فُلَانٍ قَالَ خَيْرٌ"
    no_chain = "فُلَانٍ أَنَّ رَسُولَ اللَّهِ قَالَ خَيْرٌ"
    braces = "حَدَّثَنَا فُلَانٍ {خَيْرٌ} عَنْ النَّبِيِّ"
    ahmad = parse_open_hadith_csv(fixture_path("musnad-ahmad.csv").read_bytes()).records[0].text

    for text in (dialogue, no_marker, no_chain, braces, ahmad, ""):
        assert hadith_spans(text) == [Span(0, len(text), SpanRole.BODY)]
