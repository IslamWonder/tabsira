"""
Today's (imla'i) spelling of a verse of the mushaf, for the leak guard only (task 05.9).

The stored Quran is quranpedia's Uthmani text (decision 16), and a model writes
today's spelling. The guard fold (`src.scripture.guard_fold`) brings most of
today's spelling back to the mushaf's skeleton, but it works on one text at a
time and cannot move a word boundary: the mushaf joins the vocative «يا» to the
word after it («يٰقوم», «يٰٓأيها»), today writes it apart, and a short verse
quoted as today writes it then has another word count than its folded Uthmani
text. So the guard also keeps, for every verse, the skeleton of the verse
converted here into today's spelling (`quran_verse_standard_guard`), and holds
model text against both.

The conversion is deterministic and works on the stored text alone, word by
word: marks out; alef wasla and madda as today; a waw or alef maqsura that only
carries a dagger alef written as an alef («الصلاة», «التوراة»); the dagger alef
written as an alef, except in the words today's spelling writes without it
(«ذلك», «هذا», «الرحمن»); the small high yeh written out («إبراهيم»); a final yeh
with kasra as two yehs («يحيي»); the article written whole before «ليل»; the open
teh of the nouns the mushaf writes so («رحمت») as a teh marbuta; and the vocative
written apart («يا قوم», «يا أيها», «يا أيتها», «ويا قوم»), as is the particle of attention
before «أنتم»; and the hamzas the mushaf writes on the line or on a bare tooth seated
as today seats them («يستهزئون», «الرؤيا», «نبأ», «رأى»). These rules were
chosen by measuring the converted skeletons against an independent text in
today's spelling (docs/BENCHMARK.md, «Leak guard in two spellings»).

Its output is folded at once into a guard skeleton and stored that way only: the
converted text is never stored, displayed, returned by an API or sent to a model,
and it is not scripture as any source gives it. The displayed verse stays the
stored Uthmani text, byte for byte with its hash. Code points are written as
numbers, as in `src.scripture.text`.
"""

from __future__ import annotations

import re

from src.scripture.guard_fold import guard_fold

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
_HAMZA = chr(0x0621)
_MADDA_ALEF = chr(0x0622)
_ALEF_HAMZA = chr(0x0623)
_WAW_HAMZA = chr(0x0624)
_YEH_HAMZA = chr(0x0626)
_HAMZA_ABOVE = chr(0x0654)
_HEH = chr(0x0647)
_FATHA = chr(0x064E)
_DAMMA = chr(0x064F)
_SUKUN = chr(0x0652)
_QURANIC_SUKUN = chr(0x06E1)
_TATWEEL = chr(0x0640)
_SMALL_HIGH_YEH = chr(0x06E7)
# Holds the place of an alef maqsura that stays one, while the others are rewritten.
_KEPT_MAQSURA = chr(0xFFF0)
# A conjunction or preposition, then the article, before a stem.
_PREFIXES = re.compile("^(?:[\u0648\u0641\u0628\u0644])?(?:\u0627\u0644|\u0644\u0644)?")
# The mushaf's joined vocative: a word that opens with a yeh carrying a dagger alef (and
# perhaps a maddah) is the particle «يا» and the word called. Every such word of the
# mushaf is one (349 of them), «يٰليتني» included, which today's spelling writes apart too.
_VOCATIVE = re.compile(
    f"^(?P<joined>[{_WAW}{_FEH}]?){_MARKS}*{_YEH}{_MARKS}*{_DAGGER}{_MARKS}*(?={_LETTER})"
)
YA = _YEH + _ALEF
# The particle of attention joined to «أنتم» (3:66, 3:119, 4:109, 47:38): a heh carrying a dagger
# alef before an alef with hamza; «هٰٓؤلاء» stays one word, as today writes it.
_ATTENTION = re.compile(f"^{_HEH}{_MARKS}*{_DAGGER}{_MARKS}*(?={_ALEF_HAMZA})")
HA = _HEH + _ALEF

# Hamza seats. The mushaf writes some hamzas on the line or on a bare tooth where
# today's spelling gives them a seat chosen by the vowels around them: a yeh after
# or with a kasra («يستهزئون», «أفئدة», «متكئون»), a waw after or with a damma
# («الرؤيا», «ليسوؤوا»). A hamza on the line takes one only after a short vowel; a
# tooth before an alef is today's madda («بآلهتنا») and keeps none.
_SHORT = f"[{_KASRA}{_DAMMA}]"
_LINE_HAMZA = re.compile(f"(?P<before>{_SHORT}){_HAMZA}(?P<own>[{_FATHA}{_KASRA}{_DAMMA}]?)")
_TOOTH_HAMZA = re.compile(
    f"(?P<before>[{_FATHA}{_KASRA}{_DAMMA}{_SUKUN}{_QURANIC_SUKUN}]?){_TATWEEL}+{_HAMZA_ABOVE}"
    f"(?P<own>[{_FATHA}{_KASRA}{_DAMMA}]?)(?!{_FATHA}?{_ALEF})"
)
# A final hamza on a waw before a silent alef is today a hamza on an alef: «نبؤا» is «نبأ».
_FINAL_WAW_HAMZA = re.compile(f"{_WAW_HAMZA}{_MARKS}*{_ALEF}{_MARKS}*$")
# A final «ءا» after a fatha is today «أى»: «رءا» is «رأى», «ونـٔا» is «ونأى».
_FINAL_HAMZA_ALEF = re.compile(
    f"(?<={_FATHA})(?:{_HAMZA}|{_TATWEEL}+{_HAMZA_ABOVE}){_FATHA}?{_ALEF}{_MARKS}*$"
)

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
# Nouns the mushaf ends with an open teh where today's spelling has a teh marbuta
# (رحمت، نعمت، سنت، امرأت، كلمت، شجرت، جنت، قرت، بقيت، معصيت، لعنت، ابنت، فطرت).
_OPEN_TEH = frozenset(
    {
        "\u0631\u062d\u0645\u062a",
        "\u0646\u0639\u0645\u062a",
        "\u0633\u0646\u062a",
        "\u0627\u0645\u0631\u0623\u062a",
        "\u0643\u0644\u0645\u062a",
        "\u0634\u062c\u0631\u062a",
        "\u062c\u0646\u062a",
        "\u0642\u0631\u062a",
        "\u0628\u0642\u064a\u062a",
        "\u0645\u0639\u0635\u064a\u062a",
        "\u0644\u0639\u0646\u062a",
        "\u0627\u0628\u0646\u062a",
        "\u0641\u0637\u0631\u062a",
    }
)


def standard_word(
    word: str,
    *,
    keep_alef: bool | None = None,
    open_teh: bool | None = None,
    long_yeh: bool = False,
) -> str:
    """
    Return one word of the mushaf in today's spelling, without marks.

    The choices default to today's standard; a caller may make them otherwise
    (`keep_alef` for a dagger alef, `open_teh` for a final open teh, `long_yeh` for
    a final yeh written twice), as a writer might.
    """
    raw = _seated(word).replace(_WAW + _DAGGER, _ALEF)
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
    plain = re.sub(_MARKS, "", raw).replace(_WASLA, _ALEF).replace(_SMALL_HIGH_YEH, _YEH)
    plain = plain.replace(_HAMZA + _ALEF, _MADDA_ALEF)
    bare = plain.replace(_DAGGER, "")
    alef = keep_alef if keep_alef is not None else bare not in _NO_ALEF
    plain = plain.replace(_DAGGER, _ALEF if alef else "")
    if open_teh is None:
        marbuta = _PREFIXES.sub("", plain) in _OPEN_TEH
    else:
        marbuta = open_teh and plain.endswith(_TEH) and not plain.endswith(_ALEF + _TEH)
    if marbuta:
        plain = plain[:-1] + _TEH_MARBUTA
    if long_yeh and plain.endswith(_YEH):
        plain += _YEH
    return plain


def _seat(match: re.Match[str]) -> str:
    vowels = match["before"] + match["own"]
    if _KASRA in vowels:
        seat = _YEH_HAMZA
    elif _DAMMA in vowels:
        seat = _WAW_HAMZA
    else:
        return match[0]
    return match["before"] + seat + match["own"]


def _seated(word: str) -> str:
    """Return the word with its hamzas on the seats today's spelling gives them."""
    # With a dagger alef, so the final alef maqsura is kept as one (see `standard_word`).
    word = _FINAL_HAMZA_ALEF.sub(_ALEF_HAMZA + _MAQSURA + _DAGGER, word)
    word = _FINAL_WAW_HAMZA.sub(_ALEF_HAMZA, word)
    word = _TOOTH_HAMZA.sub(_seat, word)
    return _LINE_HAMZA.sub(_seat, word)


def vocative(word: str) -> tuple[str, str] | None:
    """
    Split a word that opens with the mushaf's joined vocative, else return None.

    Returns the particle as today writes it, with the conjunction glued to it
    («يا», «ويا»), and the rest of the word.
    """
    match = _VOCATIVE.match(word)
    if match is None:
        return None
    return match["joined"] + YA, word[match.end() :]


def _attention(word: str) -> tuple[str, str] | None:
    match = _ATTENTION.match(word)
    return (HA, word[match.end() :]) if match is not None else None


def standard(text: str) -> str:
    """Return a verse of the mushaf in today's standard spelling, deterministically."""
    words: list[str] = []
    for word in text.split():
        split = vocative(word) or _attention(word)
        words.extend(
            [split[0], standard_word(split[1])] if split is not None else [standard_word(word)]
        )
    return " ".join(words)


def standard_skeleton(text: str) -> str:
    """Return the guard skeleton of a verse of the mushaf in today's spelling: all that is kept."""
    return guard_fold(standard(text))
