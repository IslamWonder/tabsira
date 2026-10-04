"""
The guard fold: one form for a text of scripture and for model text, whatever the spelling.

The leak guard compares what a model wrote with the stored verses and hadiths.
The Quran is stored in the Uthmani script of the mushaf, and a model writes the
standard (imla'i) spelling: «ٱلصَّلَوٰةَ» is «الصلاة», «ٱلسَّمَـٰوَٰتِ» is
«السماوات», «رَحْمَتِ» is «رحمة», «يُحْىِ» is «يحيي», «ذَٰلِكَ» is «ذلك». Both are
folded here to the same skeleton, so a quotation is found in either spelling:

- before the search fold, on the text as written: a waw that only carries a
  dagger alef (no vowel of its own: «صلوٰة», «زكوٰة», «حيوٰة») is that alef, a
  dagger alef inside a word after an alef maqsura is an alef («التورىٰة»), and
  the small high yeh («إبرٰهـۧم», «النبيـۧن») is a yeh;
- `search_copy`, the search fold (marks out, letter forms unified);
- then every alef and hamza is dropped, since the two spellings disagree on
  where a long ā is written (the dagger alef is a written alef in «السماوات»
  and none in «ذلك»); a word-final teh is a heh, since the Uthmani open teh
  («رحمت») is the standard teh marbuta («رحمة»); a word-final waw-heh is a heh
  («صلوة» and «صلاة»); a letter written twice in a row is one («يحيي» and
  «يحي», «مسؤول» and «مسول», «الليل» and «اليل»).

The skeleton is used on both sides of every guard comparison and for nothing
else: it is never shown and never used for retrieval, which keeps `search_copy`.
"""

from __future__ import annotations

import re

from src.scripture.text import search_copy

_WAW = chr(0x0648)
_DAGGER_ALEF = chr(0x0670)
_ALEF = chr(0x0627)
_ALEF_MAQSURA = chr(0x0649)
_SMALL_HIGH_YEH = chr(0x06E7)
_YEH = chr(0x064A)
_HEH = chr(0x0647)
_TEH = chr(0x062A)

# Harakat and Quranic marks that may sit between a letter and the next one.
_MARKS = "[\u064b-\u065f\u06d6-\u06ed\u0640]*"
_ARABIC_LETTER = "[\u0621-\u064a\u0671-\u06d3]"
# A waw that carries only a dagger alef is that alef; a waw with its own vowel stays.
_SEAT_WAW = re.compile(_WAW + _DAGGER_ALEF)
_MID_MAQSURA = re.compile(f"{_ALEF_MAQSURA}{_DAGGER_ALEF}(?={_MARKS}{_ARABIC_LETTER})")
_DROPPED = re.compile(f"[{_ALEF}{chr(0x0621)}]")
_FINAL_TEH = re.compile(f"{_TEH}(?= |$)")
_FINAL_WAW_HEH = re.compile(f"{_WAW}{_HEH}(?= |$)")
# Any letter written twice in a row is one: «يحيي» and «يحي», «الليل» and «اليل».
_DOUBLED = re.compile(r"(\w)\1+")


def guard_fold(text: str) -> str:
    """Return the guard skeleton of `text`: for leak comparisons only."""
    written = _SEAT_WAW.sub(_ALEF, text)
    written = _MID_MAQSURA.sub(_ALEF, written).replace(_SMALL_HIGH_YEH, _YEH)
    folded = _DROPPED.sub("", search_copy(written))
    folded = " ".join(folded.split())
    folded = _FINAL_TEH.sub(_HEH, folded)
    folded = _FINAL_WAW_HEH.sub(_HEH, folded)
    return _DOUBLED.sub(r"\1", folded)
