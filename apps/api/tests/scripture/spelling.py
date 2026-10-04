"""
The standard (imla'i) spelling of a stored Uthmani verse, built from the stored text.

Tests need a verse as a model would write it, in today's spelling. Typing one by
hand is not allowed (a test never carries hand-typed scripture), so the standard
spelling is derived from the stored text by the inverse of what the guard fold
undoes: marks out; alef wasla and madda as today; a waw or alef maqsura that only
carries a dagger alef written as an alef («الصلاة», «التوراة»); the dagger alef
written as an alef, except in the words today's spelling writes without it
(«ذلك», «هذا», «الرحمن»); the small high yeh written out («إبراهيم»); a final
yeh with kasra as two yehs («يحيي»); and the open teh of the words the mushaf
writes so («رحمت») as a teh marbuta. `variant` makes the spelling choices at
random instead, to sweep a sample of the store.
"""

from __future__ import annotations

import random
import re

_MARKS = "[\u064b-\u065f\u06d6-\u06e6\u06e8-\u06ed\u0640\u0610-\u061a]"
_LETTER = "[\u0621-\u064a\u0671-\u06d3\u06e7]"
_ALEF = chr(0x0627)
_DAGGER = chr(0x0670)
_WAW = chr(0x0648)
_MAQSURA = chr(0x0649)
_YEH = chr(0x064A)
_TEH = chr(0x062A)
_TEH_MARBUTA = chr(0x0629)
_KASRA = chr(0x0650)
_FATHATAN = chr(0x064B)
_SHADDA = chr(0x0651)
_WASLA = chr(0x0671)
_LAM = chr(0x0644)
_FEH = chr(0x0641)
# Holds the place of an alef maqsura that stays one, while the others are rewritten.
_KEPT_MAQSURA = chr(0xFFF0)
_PREFIXES = re.compile("^(?:[\u0648\u0641\u0628\u0644])?(?:\u0627\u0644|\u0644\u0644)?")

# Words today's spelling writes without the alef the mushaf marks with a dagger
# alef, compared bare (no marks, no dagger alef): ذلك، هذا، هذه، لكن، الرحمن، إله.
_NO_ALEF = {
    "".join(chr(code) for code in word)
    for word in (
        (0x0630, 0x0644, 0x0643),
        (0x0647, 0x0630, 0x0627),
        (0x0647, 0x0630, 0x0647),
        (0x0644, 0x0643, 0x0646),
        (0x0627, 0x0644, 0x0631, 0x062D, 0x0645, 0x0646),
        (0x0625, 0x0644, 0x0647),
    )
}
# Nouns the mushaf ends with an open teh where today's spelling has a teh marbuta.
_OPEN_TEH = {
    "رحمت",
    "نعمت",
    "سنت",
    "امرأت",
    "كلمت",
    "شجرت",
    "جنت",
    "قرت",
    "بقيت",
    "معصيت",
    "لعنت",
    "ابنت",
    "فطرت",
}


def _word(word: str, rng: random.Random | None) -> str:
    raw = word.replace(_WAW + _DAGGER, _ALEF)
    raw = re.sub(f"{_MAQSURA}{_DAGGER}(?={_MARKS}*{_LETTER})", _ALEF, raw)
    # A final yeh with kasra is the consonant; today's spelling writes the long ī after it.
    raw = re.sub(f"[{_MAQSURA}{_YEH}]{_KASRA}$", _YEH + _YEH, raw)
    # The article before «ليل» is written in full today: «الليل», not «اليل».
    raw = re.sub(
        f"^([{_WAW}{_FEH}]?){_WASLA}{_LAM}{_SHADDA}(?={_MARKS}*{_YEH})",
        r"\1" + _WASLA + _LAM + _LAM,
        raw,
    )
    # A final alef maqsura stays one when it carries a dagger alef or follows a tanwin.
    raw = re.sub(f"{_MAQSURA}{_DAGGER}{_MARKS}*$", _KEPT_MAQSURA, raw)
    raw = re.sub(f"(?<!{_FATHATAN}){_MAQSURA}(?={_MARKS}*$)", _YEH, raw)
    raw = re.sub(f"{_MAQSURA}(?={_MARKS}*{_LETTER})", _YEH, raw)
    raw = raw.replace(_KEPT_MAQSURA, _MAQSURA)
    plain = re.sub(_MARKS, "", raw).replace(_WASLA, _ALEF).replace(chr(0x06E7), _YEH)
    plain = plain.replace(chr(0x0621) + _ALEF, chr(0x0622))
    bare = plain.replace(_DAGGER, "")
    keep_alef = rng.random() < 0.5 if rng else bare not in _NO_ALEF
    plain = plain.replace(_DAGGER, _ALEF if keep_alef else "")
    stem = _PREFIXES.sub("", plain)
    open_teh = (
        plain.endswith(_TEH) and not plain.endswith(_ALEF + _TEH) and rng.random() < 0.5
        if rng
        else stem in _OPEN_TEH
    )
    if open_teh:
        plain = plain[:-1] + _TEH_MARBUTA
    if rng and plain.endswith(_YEH) and rng.random() < 0.3:
        plain += _YEH
    return plain


def standard(text: str) -> str:
    """Return `text` in today's standard spelling, deterministically."""
    return " ".join(_word(word, None) for word in text.split())


def variant(text: str, rng: random.Random) -> str:
    """Return `text` in one of the spellings a writer could use, chosen by `rng`."""
    return " ".join(_word(word, rng) for word in text.split())
