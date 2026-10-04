"""
Arabic text for matching and search.

Everything here produces a *search form*. The text people wrote, and the text the
ontology holds, is stored as it is and shown as it is; a search form is kept next
to it in its own column and never replaces it.
"""

from __future__ import annotations

import re
import unicodedata

# Marks that carry no letter: tashkeel, Quranic annotation signs, the dagger alef.
_MARKS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06dc\u06df-\u06e8\u06ea-\u06ed]")
# Invisible direction and joining controls that a copy from a web page leaves behind.
_INVISIBLE = re.compile(r"[\u061c\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]")
_NOT_A_WORD_CHARACTER = re.compile(r"[\W_]+")

# One letter for each group of spellings people use interchangeably in a search
# box: the alef carriers, the two yehs and the Persian yeh, teh marbuta, the hamza
# on waw and on the yeh seat, the Persian kaf. The tatweel is deleted.
_FOLD = str.maketrans("أإآٱىیئةؤک", "اااايييهوك", "\N{ARABIC TATWEEL}")
_ASCII_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

ARTICLE = "ال"
# What must remain of a word once its article is removed, so a two-letter word is not cut to one letter.
# Particles fused to the article («وال», «بال», «لل») are left alone: cutting them
# turns «والدين» (parents) into «دين» (religion), a false exact match.
_MIN_STEM = 2

_ARABIC_LETTER = re.compile(r"[\u0621-\u064a\u066e-\u06d3\u06fa-\u06fc]")
_LIST_SEPARATORS = re.compile("[،,؛;\n]")


def normalize_arabic(text: str) -> str:
    """
    Return the search form of `text`.

    Marks and tatweel are removed, the alef, yeh, teh marbuta and hamza carriers
    are folded, digits become ASCII, every run of punctuation and spaces becomes
    one space, and Latin letters are lower-cased. The result is for comparison
    only; calling it twice gives the same string.
    """
    folded = unicodedata.normalize("NFKC", text)
    folded = _INVISIBLE.sub("", folded)
    folded = _MARKS.sub("", folded).translate(_FOLD).translate(_ASCII_DIGITS)
    return _NOT_A_WORD_CHARACTER.sub(" ", folded.casefold()).strip()


def strip_article(word: str) -> str:
    """Return `word` (already in search form) without its definite article, when a stem remains."""
    if word.startswith(ARTICLE) and len(word) - len(ARTICLE) >= _MIN_STEM:
        return word[len(ARTICLE) :]
    return word


def tokens(text: str) -> list[str]:
    """Return the words of `text` in search form, in order."""
    normalized = normalize_arabic(text)
    return normalized.split(" ") if normalized else []


def bare_form(text: str) -> str:
    """Return the search form of `text` with the definite article removed from every word."""
    return " ".join(strip_article(word) for word in tokens(text))


def search_variants(text: str) -> list[str]:
    """
    Return the forms of `text` an entity label could be spelt in, most exact first.

    A detector or a vision model writes «السماء»; the ontology keeps «سماء», and
    the other way round for «الكعبة». So the search form comes first, then the same
    with the article removed from every word, then that with the article put back
    on the first word.
    """
    exact = normalize_arabic(text)
    if not exact:
        return []
    bare = bare_form(text)
    first, *rest = bare.split(" ")
    with_article = " ".join([first if first.startswith(ARTICLE) else ARTICLE + first, *rest])
    return list(dict.fromkeys([exact, bare, with_article]))


def contains_arabic(text: str) -> bool:
    """Return whether `text` holds at least one Arabic letter."""
    return _ARABIC_LETTER.search(text) is not None


def split_list(value: str) -> list[str]:
    """
    Split a list column into its items.

    The workbook separates items with the Arabic comma; the other separators are
    accepted so a hand-edited cell does not collapse into one long item. Items are
    trimmed and an empty item is dropped. The words themselves are not touched.
    """
    return [item.strip() for item in _LIST_SEPARATORS.split(value) if item.strip()]
