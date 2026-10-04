"""
Where a reader checks a text at its source: the quranpedia verse, the dorar.net search.

quranpedia (checked on its pages, 4 October 2026): the page of a surah in a
mushaf is `https://quranpedia.net/surah/{mushaf}/{surah}` (its canonical URL),
and each verse in it carries the anchor `verse-{quranpedia ayah id}`, so the
link opens mushaf 2 at the verse itself.

dorar.net cannot be fetched from the server (decision 18), so its link is a
search the reader runs: `https://dorar.net/hadith/search?q=<words>&st=w`
(`st=w`: every word must appear, in any order). The format was taken from the
dorar.net site search as used by open-source clients; an owner must still open
a few of these links in a browser to confirm them (docs/ASSET_MANIFEST.md).
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

from src.scripture.quranpedia import MUSHAF_ID, SITE_URL
from src.scripture.spans import SpanRole, hadith_spans
from src.scripture.text import search_copy, without_marks

DORAR_SEARCH_URL = "https://dorar.net/hadith/search"
DORAR_QUERY_WORDS = 7
# Folded words every hadith shares: the marker and the honorific say nothing about which one it is.
_COMMON = frozenset(
    [
        "قال",
        "ان",
        "عن",
        "رسول",
        "الله",
        "النبي",
        "صلي",
        "عليه",
        "وسلم",
        "رضي",
        "عنه",
        "عنها",
        "عنهما",
        "يقول",
        "سمعت",
    ]
)


_WORDS = re.compile(r"[^\W\d_]+")


def quranpedia_verse_url(surah: int, quranpedia_ayah_id: int) -> str:
    """Return the quranpedia page of mushaf 2 that shows this verse, anchored on it."""
    return f"{SITE_URL}/surah/{MUSHAF_ID}/{surah}#verse-{quranpedia_ayah_id}"


def distinctive_words(text: str) -> list[str]:
    """
    Return a few words, diacritics removed, that pick this hadith out on a search engine.

    The Prophet's quoted words when they were found, else the body after the
    chain, else the middle of the text, where the chain has usually ended.
    Marker words and the honorific are left out.
    """
    spans = {span.role: span for span in hadith_spans(text)}
    chosen = spans.get(SpanRole.WORDS, spans[SpanRole.BODY])
    words = [
        word
        for word in _WORDS.findall(without_marks(text[chosen.start : chosen.end]))
        if search_copy(word) not in _COMMON and len(word) > 1
    ]
    if SpanRole.CHAIN not in spans:
        words = words[len(words) // 2 :]
    return words[:DORAR_QUERY_WORDS]


def dorar_search_url(text: str) -> str:
    """Return the dorar.net search for this hadith, for the reader to open."""
    query = " ".join(distinctive_words(text))
    return f"{DORAR_SEARCH_URL}?{urlencode({'q': query, 'st': 'w'})}"
