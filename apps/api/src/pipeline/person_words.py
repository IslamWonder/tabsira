"""
Person descriptors the scene stage may not keep (v2 §0.6 and §6).

The vision model is told to call every person «شخص» and to state no one's religion, age,
gender, ethnicity, health or intent. The server does not take that on trust: every free
text of the scene is checked for a word that names a person by one of these, and the word
is replaced by the neutral one («شخص», «أشخاص»; "person", "people"). Clothing, symbols and
religious objects are allowed as objects («حجاب», «سجادة», «مسجد» stay); a word that turns
them into a conclusion about a person («محجبة») is not. The list is short on purpose: it
names the words the prompt forbids and their common forms, and a replacement is recorded in
the scene's `rejected` so the trace says what the server changed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PERSON = "شخص"
PERSONS = "أشخاص"
PERSON_EN = "person"
PERSONS_EN = "people"

# Arabic words that name a person by gender, age or religion, with their neutral form.
# Dual forms keep «شخصان»; plurals become «أشخاص».
ARABIC: dict[str, str] = {
    # Gender
    "رجل": PERSON,
    "رجلان": "شخصان",
    "رجلين": "شخصين",
    "رجال": PERSONS,
    "امرأة": PERSON,
    # The definite form drops the first letter: «المرأة» is the article and this stem.
    "مرأة": PERSON,
    "امرأتان": "شخصان",
    "امرأتين": "شخصين",
    "نساء": PERSONS,
    "سيدة": PERSON,
    "سيدات": PERSONS,
    "فتاة": PERSON,
    "فتيات": PERSONS,
    "فتى": PERSON,
    "فتيان": PERSONS,
    "بنت": PERSON,
    "بنات": PERSONS,
    "ولد": PERSON,
    "أولاد": PERSONS,
    "اولاد": PERSONS,
    "صبي": PERSON,
    "صبية": PERSONS,
    "غلام": PERSON,
    "شاب": PERSON,
    "شابة": PERSON,
    "شباب": PERSONS,
    # Age
    "طفل": PERSON,
    "طفلة": PERSON,
    "أطفال": PERSONS,
    "اطفال": PERSONS,
    "رضيع": PERSON,
    "رضيعة": PERSON,
    "مراهق": PERSON,
    "مراهقة": PERSON,
    "مراهقون": PERSONS,
    "مسن": PERSON,
    "مسنة": PERSON,
    "مسنون": PERSONS,
    "مسنين": PERSONS,
    "عجوز": PERSON,
    "عجائز": PERSONS,
    "كهل": PERSON,
    "شيخ": PERSON,
    "شيوخ": PERSONS,
    # Religion, as a conclusion about a person (objects such as «حجاب» are not here)
    "مسلم": PERSON,
    "مسلمة": PERSON,
    "مسلمون": PERSONS,
    "مسلمين": PERSONS,
    "مسلمات": PERSONS,
    "مسيحي": PERSON,
    "مسيحية": PERSON,
    "مسيحيون": PERSONS,
    "يهودي": PERSON,
    "يهودية": PERSON,
    "يهود": PERSONS,
    "محجبة": PERSON,
    "محجبات": PERSONS,
    "منقبة": PERSON,
    "منقبات": PERSONS,
    "متدين": PERSON,
    "متدينة": PERSON,
    "راهب": PERSON,
    "راهبة": PERSON,
    "كاهن": PERSON,
}

# English words of the entity label, lower case; the label becomes "person" or "people".
ENGLISH: dict[str, str] = {
    "man": PERSON_EN,
    "men": PERSONS_EN,
    "woman": PERSON_EN,
    "women": PERSONS_EN,
    "lady": PERSON_EN,
    "ladies": PERSONS_EN,
    "gentleman": PERSON_EN,
    "guy": PERSON_EN,
    "guys": PERSONS_EN,
    "boy": PERSON_EN,
    "boys": PERSONS_EN,
    "girl": PERSON_EN,
    "girls": PERSONS_EN,
    "child": PERSON_EN,
    "children": PERSONS_EN,
    "kid": PERSON_EN,
    "kids": PERSONS_EN,
    "baby": PERSON_EN,
    "babies": PERSONS_EN,
    "toddler": PERSON_EN,
    "teenager": PERSON_EN,
    "teenagers": PERSONS_EN,
    "teen": PERSON_EN,
    "elderly": PERSON_EN,
    "senior": PERSON_EN,
    "old": PERSON_EN,
    "muslim": PERSON_EN,
    "muslims": PERSONS_EN,
    "christian": PERSON_EN,
    "christians": PERSONS_EN,
    "jew": PERSON_EN,
    "jews": PERSONS_EN,
    "jewish": PERSON_EN,
    "hijabi": PERSON_EN,
    "veiled": PERSON_EN,
    "nun": PERSON_EN,
    "monk": PERSON_EN,
    "priest": PERSON_EN,
}

# Conjunctions, the article and the one-letter prepositions a word may carry; the longest first.
_PREFIXES = ("وبال", "وال", "فال", "بال", "كال", "ولل", "لل", "ال", "و", "ف", "ب", "ل", "ك", "")
# Harakat, tanwin, superscript alef, Quranic marks and tatweel: removed before matching only.
_MARKS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
# The punctuation a token may carry before and after its word; it stays where it is. Harakat
# are not listed: they belong to the word and are removed with it.
_PUNCT = "«»\"'()\\[\\]{}،؛؟!.,:;\\-\u2013\u2014\u2026"
_ARABIC_CORE = re.compile(rf"^([{_PUNCT}]*)(.*?)([{_PUNCT}]*)$", re.DOTALL)
# The accusative tanwin is written with an alef after the word: «طفلًا».
_FATHATAN = "\u064b"
_ALEF = "\u0627"
_ENGLISH_WORD = re.compile(r"[a-z]+")


@dataclass(frozen=True, slots=True)
class Neutralised:
    """A text with its person descriptors replaced, and the words that were."""

    text: str
    replaced: tuple[str, ...]

    @property
    def changed(self) -> bool:
        return bool(self.replaced)


def _arabic_match(word: str) -> tuple[str, str] | None:
    """Return the prefix kept and the neutral word, when `word` names a person by a descriptor."""
    bare = _MARKS.sub("", word)
    forms = [bare]
    if _FATHATAN in word and bare.endswith(_ALEF):
        forms.append(bare[:-1])
    for form in forms:
        for prefix in _PREFIXES:
            if form.startswith(prefix) and (stem := form[len(prefix) :]) in ARABIC:
                return prefix, ARABIC[stem]
    return None


def neutralise_arabic(text: str) -> Neutralised:
    """Replace, word by word, every Arabic person descriptor in `text` by the neutral word."""
    pieces: list[str] = []
    replaced: list[str] = []
    for token in re.split(r"(\s+)", text):
        match = _ARABIC_CORE.match(token)
        head, core, tail = match.groups() if match else ("", token, "")
        found = _arabic_match(core) if core else None
        if found is None:
            pieces.append(token)
            continue
        prefix, neutral = found
        replaced.append(_MARKS.sub("", core))
        pieces.append(f"{head}{prefix}{neutral}{tail}")
    return Neutralised("".join(pieces), tuple(replaced))


def neutralise_arabic_label(label: str) -> Neutralised:
    """Return the whole label as «شخص» or «أشخاص» when any of its words is a descriptor."""
    result = neutralise_arabic(label)
    if not result.changed:
        return result
    forms = [found[1] for word in result.replaced if (found := _arabic_match(word)) is not None]
    return Neutralised(
        PERSONS if any(form != PERSON for form in forms) else PERSON, result.replaced
    )


def neutralise_english_label(label: str) -> Neutralised:
    """Return the whole label as "person" or "people" when any of its words is a descriptor."""
    words = _ENGLISH_WORD.findall(label.lower())
    hits = [word for word in words if word in ENGLISH]
    if not hits:
        return Neutralised(label, ())
    plural = any(ENGLISH[word] == PERSONS_EN for word in hits)
    return Neutralised(PERSONS_EN if plural else PERSON_EN, tuple(hits))
