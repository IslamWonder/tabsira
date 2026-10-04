"""
The two things done to scripture text: hashing it as it is, and folding a copy for search.

`sha256_hex` hashes the exact UTF-8 bytes; the database checks the same hash on
every stored row. `search_copy` returns a folded copy for matching and search
only. It is stored apart from the text (`quran_verse_search`, `hadith_search`)
and is never displayed: the displayed text is always the stored original.

Code points are written as numbers on purpose: an Arabic letter beside a Latin
one, or an invisible direction mark, is easy to misread in source code.
"""

from __future__ import annotations

import hashlib
import re

ALEF = 0x0627
HAMZA = 0x0621
WAW = 0x0648
YEH = 0x064A
KAF = 0x0643
HEH = 0x0647

# Harakat, Quranic annotation marks and small letters, tatweel, and the
# invisible direction and joining controls some sources carry.
_DROPPED = [
    *range(0x0610, 0x061B),
    *range(0x064B, 0x0660),
    0x0670,  # superscript alef
    0x0640,  # tatweel
    *range(0x06D6, 0x06EE),
    *range(0x08D3, 0x0900),
    0x061C,  # Arabic letter mark
    *range(0x200B, 0x2010),  # zero-width space, joiners, LRM, RLM
    *range(0x202A, 0x202F),  # embeddings and overrides
    *range(0x2066, 0x206A),  # isolates
    0xFEFF,  # byte order mark
]

_FOLDED = {
    # Every alif form, alif wasla included, is a plain alif.
    0x0622: ALEF,
    0x0623: ALEF,
    0x0625: ALEF,
    0x0671: ALEF,
    0x0672: ALEF,
    0x0673: ALEF,
    0x0675: ALEF,
    # A hamza on a seat is its seat; alif maqsura and the Persian forms are folded too.
    0x0624: WAW,
    0x0626: YEH,
    0x0649: YEH,
    0x06CC: YEH,
    0x06A9: KAF,
    0x0629: HEH,  # teh marbuta
}

# The honorific ligature, written out as most hadith texts spell it.
_HONORIFIC = 0xFDFA
_HONORIFIC_WORDS = " ".join(
    "".join(chr(code) for code in word)
    for word in (
        (0x0635, 0x0644, 0x064A),
        (ALEF, 0x0644, 0x0644, HEH),
        (0x0639, 0x0644, 0x064A, HEH),
        (WAW, 0x0633, 0x0644, 0x0645),
    )
)

_TABLE: dict[int, int | str | None] = {
    **dict.fromkeys(_DROPPED),
    **_FOLDED,
    _HONORIFIC: f" {_HONORIFIC_WORDS} ",
}
_MARKS_TABLE: dict[int, None] = dict.fromkeys(_DROPPED)
# The Uthmani script writes a madda alif as hamza then alif.
_UTHMANI_MADDA = chr(HAMZA) + chr(ALEF)
# Anything that is not an Arabic letter, a digit or a Latin letter separates words.
_SEPARATORS = re.compile(f"[^{chr(HAMZA)}-{chr(YEH)}0-9{chr(0x0660)}-{chr(0x0669)}a-zA-Z]+")


def sha256_hex(text: str) -> str:
    """Return the SHA-256 of the exact UTF-8 bytes of `text`, in lower-case hex."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def search_copy(text: str) -> str:
    """
    Return the folded copy of `text` used for search and matching only.

    Diacritics, Quranic marks and direction controls are removed, alif (and
    the Uthmani hamza-alif), hamza seats, yeh and teh marbuta are folded,
    punctuation becomes a space, and runs of spaces collapse to one. The
    result is never shown to anyone.
    """
    folded = text.translate(_TABLE).replace(_UTHMANI_MADDA, chr(ALEF))
    return _SEPARATORS.sub(" ", folded).strip()


def without_marks(text: str) -> str:
    """
    Return `text` with diacritics, Quranic marks and direction controls removed, letters kept.

    For building a query for another site's search, never for display.
    """
    return text.translate(_MARKS_TABLE)


def folded_with_positions(text: str) -> tuple[str, list[int]]:
    """
    Fold `text` character by character and say where each folded character came from.

    The same folding as `search_copy`, except that separators are kept one for
    one (as spaces) and nothing is collapsed, so a match found in the folded
    string can be mapped back to a position in the original text. Used to find
    positions in a stored text without ever changing it.
    """
    folded: list[str] = []
    positions: list[int] = []
    for index, char in enumerate(text):
        for piece in char.translate(_TABLE):
            folded.append(" " if _SEPARATORS.fullmatch(piece) else piece)
            positions.append(index)
    return "".join(folded), positions
