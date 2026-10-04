"""
LeakGuard: refuse model text that looks like scripture.

A model never writes Quran or hadith text: it cites evidence ids, and the
server puts the stored text in the answer (v2 §0 and §10). The guard checks
every free-text field a model returns and reports what looks like a quotation:

- Quranic annotation marks (U+06D6 to U+06ED: small high ligatures, pause
  marks, end of ayah, rub el hizb) and the other Quran-only signs;
- the ornate parentheses that frame a verse (U+FD3E, U+FD3F);
- a quoted span after an introducer such as «قال تعالى», «قال رسول الله» or a
  bare «قال», or the words that follow «قال تعالى:» even without quotes;
- a very long quotation of any Arabic text;
- a run of fully vocalised words, the way scripture is written and prose is not.

Detectors are pluggable: `ShingleOverlapDetector` compares the text with a
corpus by word n-grams, and is added to the guard once the scripture store
exists (`LeakGuard([PatternLeakDetector(), ShingleOverlapDetector(verses)])`).
A finding names its kind and never copies the suspected text.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum

from pydantic import computed_field

from src.pipeline.schemas import FrozenModel

# Harakat, superscript alef and the Quranic annotation marks; removed to compare text.
_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u08D3-\u08FF\u0640]")
_ALEF = re.compile(r"[\u0622\u0623\u0625\u0671\u0672\u0673]")
_NON_LETTER = re.compile(r"[^\u0621-\u064A0-9a-z]+")
# Alef maqsura is written as ya, ta marbuta as ha.
_UNIFY = str.maketrans({0x0649: 0x064A, 0x0629: 0x0647})

_QURAN_MARKS = re.compile(r"[\u06D6-\u06ED]")
_QURAN_SIGNS = re.compile(r"[\u08F0-\u08F3\uFDFD]")
_ORNATE_BRACKETS = re.compile(r"[\uFD3E\uFD3F]")
_HARAKA = re.compile(r"[\u064B-\u0652]")
_ARABIC_WORD = re.compile(r"[\u0621-\u064A\u0671-\u06D3\u064B-\u0652\u0670\u0640]+")

_OPEN_QUOTES = "«\"“'"
_CLOSE_QUOTES = "»\"”'"
_QUOTED = f"[{_OPEN_QUOTES}]([^{_CLOSE_QUOTES}]+)[{_CLOSE_QUOTES}]"

# Matched on text without diacritics. «قال تعالى», «يقول الله عز وجل», «قال رسول الله»,
# «قال النبي ﷺ», «صلى الله عليه وسلم», «في الآية», «في الحديث», «قوله تعالى».
_STRONG_INTRODUCER = (
    r"(?<!\w)(?:(?:و|ف)?(?:قال|يقول|قوله)\s+(?:الله\s+)?(?:تعالى|عز\s+وجل|سبحانه(?:\s+وتعالى)?|جل\s+جلاله)"
    r"|(?:و|ف)?(?:قال|يقول)\s+(?:رسول\s+الله|النبي|نبينا)(?:\s*ﷺ)?"
    r"|صلى\s+الله\s+عليه\s+وسلم|ﷺ"
    r"|(?:في|فى)\s+(?:الآية|الاية|الحديث)(?:\s+الشريف|\s+الكريمة)?)"
)
_WEAK_INTRODUCER = r"(?<!\w)(?:(?:و|ف)?(?:قال|قالت|قالوا|يقول|تقول))"
_STRONG_QUOTE = re.compile(_STRONG_INTRODUCER + r"\s*[:،,]?\s*" + _QUOTED)
_WEAK_QUOTE = re.compile(_WEAK_INTRODUCER + r"\s*[:،,]?\s*" + _QUOTED)
_STRONG_COLON = re.compile(_STRONG_INTRODUCER + r"\s*:\s*([^.؟!?\n]+)")
_ANY_QUOTE = re.compile(_QUOTED)

STRONG_QUOTE_WORDS = 3
WEAK_QUOTE_WORDS = 6
UNQUOTED_WORDS = 6
LONG_QUOTE_WORDS = 15
VOCALISED_RUN = 6
VOCALISED_MARKS = 2
SHINGLE_WORDS = 5


class LeakKind(StrEnum):
    """What made a text look like scripture."""

    QURAN_MARKS = "quran_marks"
    QURAN_SIGNS = "quran_signs"
    ORNATE_BRACKETS = "ornate_brackets"
    INTRODUCED_QUOTE = "introduced_quote"
    LONG_QUOTE = "long_quote"
    VOCALISED_SPAN = "vocalised_span"
    CORPUS_OVERLAP = "corpus_overlap"


class LeakFinding(FrozenModel):
    """One reason to refuse a text; never a copy of the suspected words."""

    kind: LeakKind
    detail: str


class LeakVerdict(FrozenModel):
    """The findings on one text; any finding refuses it."""

    findings: list[LeakFinding]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def leaked(self) -> bool:
        return bool(self.findings)


class LeakDetector(ABC):
    """Finds scripture-like content in a text."""

    @abstractmethod
    def find(self, text: str) -> list[LeakFinding]:
        """Return the findings on `text`; empty when it looks clean."""


class ScriptureLeakError(Exception):
    """Model text was refused by the leak guard; `fields` names where."""

    def __init__(self, fields: Mapping[str, LeakVerdict]) -> None:
        kinds = sorted({finding.kind.value for v in fields.values() for finding in v.findings})
        super().__init__(f"scripture-like text in {', '.join(fields)} ({', '.join(kinds)})")
        self.fields = dict(fields)


def normalize_arabic(text: str) -> str:
    """Return a comparison form: no marks, one alef, alef maqsura and ta marbuta unified."""
    stripped = _DIACRITICS.sub("", text)
    unified = _ALEF.sub(chr(0x0627), stripped).translate(_UNIFY)
    return " ".join(_NON_LETTER.sub(" ", unified.lower()).split())


def arabic_word_count(text: str) -> int:
    return len(_ARABIC_WORD.findall(text))


class PatternLeakDetector(LeakDetector):
    """The rules that need no corpus: marks, brackets, introduced quotes, vocalisation."""

    def find(self, text: str) -> list[LeakFinding]:
        findings = [
            LeakFinding(kind=kind, detail=f"{len(pattern.findall(text))} characters")
            for kind, pattern in (
                (LeakKind.QURAN_MARKS, _QURAN_MARKS),
                (LeakKind.QURAN_SIGNS, _QURAN_SIGNS),
                (LeakKind.ORNATE_BRACKETS, _ORNATE_BRACKETS),
            )
            if pattern.search(text)
        ]
        findings += self._quotes(_DIACRITICS.sub("", text))
        run = _longest_vocalised_run(text)
        if run >= VOCALISED_RUN:
            findings.append(
                LeakFinding(kind=LeakKind.VOCALISED_SPAN, detail=f"{run} fully vocalised words")
            )
        return findings

    @staticmethod
    def _quotes(plain: str) -> list[LeakFinding]:
        rules = (
            (_STRONG_QUOTE, STRONG_QUOTE_WORDS, "quotation after a scripture introducer"),
            (_STRONG_COLON, UNQUOTED_WORDS, "words after a scripture introducer and a colon"),
            (_WEAK_QUOTE, WEAK_QUOTE_WORDS, "quotation after «قال»"),
        )
        for pattern, minimum, label in rules:
            for match in pattern.finditer(plain):
                words = arabic_word_count(match.group(1))
                if words >= minimum:
                    detail = f"{label}: {words} words"
                    return [LeakFinding(kind=LeakKind.INTRODUCED_QUOTE, detail=detail)]
        for match in _ANY_QUOTE.finditer(plain):
            words = arabic_word_count(match.group(1))
            if words >= LONG_QUOTE_WORDS:
                detail = f"quotation of {words} Arabic words"
                return [LeakFinding(kind=LeakKind.LONG_QUOTE, detail=detail)]
        return []


def _longest_vocalised_run(text: str) -> int:
    longest = current = 0
    for word in _ARABIC_WORD.findall(text):
        current = current + 1 if len(_HARAKA.findall(word)) >= VOCALISED_MARKS else 0
        longest = max(longest, current)
    return longest


class ShingleOverlapDetector(LeakDetector):
    """Reports text that shares a run of words with a corpus (the scripture store, later)."""

    def __init__(self, corpus: Iterable[str], *, window: int = SHINGLE_WORDS) -> None:
        self._window = window
        self._shingles = {
            shingle for text in corpus for shingle in _shingles(normalize_arabic(text), window)
        }

    def find(self, text: str) -> list[LeakFinding]:
        shared = sum(
            1
            for shingle in _shingles(normalize_arabic(text), self._window)
            if shingle in self._shingles
        )
        if not shared:
            return []
        detail = f"{shared} runs of {self._window} words found in the corpus"
        return [LeakFinding(kind=LeakKind.CORPUS_OVERLAP, detail=detail)]


def _shingles(normalized: str, window: int) -> list[tuple[str, ...]]:
    words = normalized.split()
    return [tuple(words[index : index + window]) for index in range(len(words) - window + 1)]


class LeakGuard:
    """Runs every detector on model text."""

    def __init__(self, detectors: Sequence[LeakDetector] | None = None) -> None:
        self._detectors: tuple[LeakDetector, ...] = (
            tuple(detectors) if detectors is not None else (PatternLeakDetector(),)
        )

    def check(self, text: str) -> LeakVerdict:
        return LeakVerdict(
            findings=[finding for detector in self._detectors for finding in detector.find(text)]
        )

    def ensure_clean(self, fields: Mapping[str, str]) -> None:
        """Raise ScriptureLeakError naming every field whose text is refused."""
        refused = {
            name: verdict for name, text in fields.items() if (verdict := self.check(text)).leaked
        }
        if refused:
            raise ScriptureLeakError(refused)
