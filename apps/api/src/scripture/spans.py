"""
Display spans of a stored hadith: where the chain, the body, the Prophet's words and the notes are.

The text is never cut or changed: a span is a pair of positions in the stored
text, and the spans of a hadith always follow each other from the first
character to the last, so joining their slices gives the stored text back
(a property test holds this). The web app sets the chain and the closing notes
smaller and the Prophet's words stronger (docs/DESIGN_DECISION.md, «Hadith
display»).

The cut is made only when the text says plainly where it goes:

- the chain ends where the first «أن/قال/عن/سمعت رسول الله» or «… النبي»
  marker begins, and only if what comes before it reads like a chain
  (a transmission word, no quotation, no Quranic braces);
- the Prophet's words are the one quoted passage after that marker; when the
  source never closes the quote they run to the end; what follows a closing
  quote is the tail, unless it is only punctuation;
- a hadith with two quoted passages or more (a dialogue) keeps its body whole.

Anything else, or any doubt, gives a single `body` span covering the whole text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from src.scripture.text import folded_with_positions


class SpanRole(StrEnum):
    CHAIN = "chain"
    BODY = "body"
    WORDS = "words"
    TAIL = "tail"


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    role: SpanRole


# Folded forms (see src/scripture/text.py): no diacritics, one alif, ya for alif maqsura.
_MARKER = re.compile(
    r"(?<!\S)(?:ان|قال|عن|سمعت|سمعنا|سالت|رايت)\s+(?:رسول\s+الله|النبي|نبي\s+الله)(?!\S)"
)
_TRANSMISSION = re.compile(r"(?<!\S)(?:حدثنا|حدثني|اخبرنا|اخبرني|انبانا|عن|سمعت)(?!\S)")
_CLOSING = {'"': '"', "«": "»", "“": "”"}
_NOT_A_CHAIN = re.compile('["«»“”{}]')
_WORD = re.compile(r"\w")


def _whole(text: str) -> list[Span]:
    return [Span(0, len(text), SpanRole.BODY)]


def _chain_end(text: str) -> int | None:
    """Return where the body starts when the text has a clear chain, else None."""
    folded, positions = folded_with_positions(text)
    marker = _MARKER.search(folded)
    if marker is None:
        return None
    end = positions[marker.start()]
    chain = text[:end]
    if not _TRANSMISSION.search(folded[: marker.start()]) or _NOT_A_CHAIN.search(chain):
        return None
    return end


def _quoted_passages(text: str, start: int) -> list[tuple[int, int]]:
    """Return the (open, end) positions of every quoted passage from `start` on."""
    passages: list[tuple[int, int]] = []
    position = start
    while True:
        openings = [
            index for index in (text.find(mark, position) for mark in _CLOSING) if index >= 0
        ]
        if not openings:
            return passages
        opening = min(openings)
        closing = text.find(_CLOSING[text[opening]], opening + 1)
        if closing < 0:
            passages.append((opening, len(text)))
            return passages
        passages.append((opening, closing + 1))
        position = closing + 1


def hadith_spans(text: str) -> list[Span]:
    """Return the display spans of `text`, in order, covering it exactly."""
    body_start = _chain_end(text)
    if body_start is None:
        return _whole(text)
    passages = _quoted_passages(text, body_start)
    if len(passages) > 1:
        return _whole(text)
    chain = Span(0, body_start, SpanRole.CHAIN)
    if not passages:
        return [chain, Span(body_start, len(text), SpanRole.BODY)]
    opening, words_end = passages[0]
    if not _WORD.search(text[words_end:]):
        words_end = len(text)
    spans = [
        chain,
        Span(body_start, opening, SpanRole.BODY),
        Span(opening, words_end, SpanRole.WORDS),
    ]
    if words_end < len(text):
        spans.append(Span(words_end, len(text), SpanRole.TAIL))
    return spans
