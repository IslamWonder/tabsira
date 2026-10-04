"""
References to scripture as short keys, and their resolution to stored rows.

A key names a text without carrying it: `Q:30:50` is a verse, `Q:3:190-191` a
run of verses, `Q:112` a whole surah, `H:bukhari:1032` a hadith by the stored
number of its book. The learning path writes its hadith anchors with the
sunnah.com numbering instead (`Numbering.SUNNAH_COM`), which for Muslim is Abd
al-Baqi's: `H:muslim:8a` is the first narration of hadith 8 (stored as
`arabicnumber` `8.01`), not the stored hadith 8. `resolve_*` turn keys into the
ids of stored rows; a key that names nothing stored resolves to nothing, never
to a guess.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Hadith, QuranVerse

_QURAN = re.compile(r"^Q:(\d{1,3})(?::(\d{1,3})(?:-(\d{1,3}))?)?$")
_HADITH = re.compile(r"^H:([a-z]+):([0-9]+(?:\.[0-9]+)?)([a-z]?)$")
# sunnah.com writes the narrations of one Muslim hadith a, b, c ...
_LETTERS = "abcdefghijklmnopqrstuvwxyz"
# The books whose sunnah.com number is not the stored one (docs/ASSET_MANIFEST.md §3.1).
ABD_AL_BAQI_NUMBERED = frozenset({"muslim"})


class Numbering(StrEnum):
    """Which numbering a hadith key uses."""

    STORED = "stored"  # the dataset's own `number`, as stored
    SUNNAH_COM = "sunnah.com"  # the learning path's anchors


class BadReferenceError(ValueError):
    """A key that is not a Quran or hadith reference."""


@dataclass(frozen=True, slots=True)
class VerseRange:
    """Verses `first` to `last` of a surah; `last` None means to the end of the surah."""

    surah: int
    first: int
    last: int | None

    def contains(self, surah: int, ayah: int) -> bool:
        return (
            surah == self.surah and ayah >= self.first and (self.last is None or ayah <= self.last)
        )


@dataclass(frozen=True, slots=True)
class HadithKey:
    """A hadith by book and number, as the key wrote it."""

    collection: str
    number: str
    narration: str = ""


def parse_quran(key: str) -> VerseRange:
    match = _QURAN.match(key.strip())
    if match is None:
        message = f"{key!r} is not a Quran reference such as Q:30:50 or Q:3:190-191"
        raise BadReferenceError(message)
    surah, first, last = match.groups()
    if first is None:
        return VerseRange(int(surah), 1, None)
    return VerseRange(int(surah), int(first), int(last) if last else int(first))


def parse_hadith(key: str) -> HadithKey:
    match = _HADITH.match(key.strip())
    if match is None:
        message = f"{key!r} is not a hadith reference such as H:bukhari:1032"
        raise BadReferenceError(message)
    collection, number, narration = match.groups()
    return HadithKey(collection, number, narration)


def is_quran(key: str) -> bool:
    return key.strip().startswith("Q:")


def quran_key(surah: int, ayah: int) -> str:
    return f"Q:{surah}:{ayah}"


def hadith_key(collection: str, number: str) -> str:
    return f"H:{collection}:{number}"


async def resolve_verses(session: AsyncSession, keys: Iterable[str]) -> dict[str, list[int]]:
    """Return, for each Quran key, the ids of the stored verses it covers (in order)."""
    ranges = {key: parse_quran(key) for key in keys}
    if not ranges:
        return {}
    surahs = sorted({verse_range.surah for verse_range in ranges.values()})
    rows = (
        await session.execute(
            select(QuranVerse.id, QuranVerse.surah, QuranVerse.ayah)
            .where(QuranVerse.surah.in_(surahs))
            .order_by(QuranVerse.surah, QuranVerse.ayah)
        )
    ).all()
    return {
        key: [row.id for row in rows if verse_range.contains(row.surah, row.ayah)]
        for key, verse_range in ranges.items()
    }


def _arabic_numbers(key: HadithKey) -> tuple[str, ...]:
    """Return the `arabicnumber` values a sunnah.com Muslim reference stands for."""
    if key.narration:
        return (f"{key.number}.{_LETTERS.index(key.narration) + 1:02d}",)
    return (key.number, f"{key.number}.01")


async def resolve_hadiths(
    session: AsyncSession, keys: Iterable[str], numbering: Numbering = Numbering.STORED
) -> dict[str, list[int]]:
    """Return, for each hadith key, the id of the stored hadith it names (none when absent)."""
    parsed = {key: parse_hadith(key) for key in keys}
    if not parsed:
        return {}

    def by_arabic_number(item: HadithKey) -> bool:
        return numbering is Numbering.SUNNAH_COM and item.collection in ABD_AL_BAQI_NUMBERED

    by_number = [
        (item.collection, item.number) for item in parsed.values() if not by_arabic_number(item)
    ]
    by_arabic = [
        (item.collection, number)
        for item in parsed.values()
        if by_arabic_number(item)
        for number in _arabic_numbers(item)
    ]
    conditions = []
    if by_number:
        conditions.append(tuple_(Hadith.collection, Hadith.number).in_(by_number))
    if by_arabic:
        conditions.append(tuple_(Hadith.collection, Hadith.arabic_number).in_(by_arabic))
    rows = (
        await session.execute(
            select(Hadith.id, Hadith.collection, Hadith.number, Hadith.arabic_number).where(
                or_(*conditions)
            )
        )
    ).all()
    found: dict[str, list[int]] = {}
    for key, item in parsed.items():
        if by_arabic_number(item):
            ids = [
                row.id
                for number in _arabic_numbers(item)
                for row in rows
                if row.collection == item.collection and row.arabic_number == number
            ]
        else:
            ids = [
                row.id
                for row in rows
                if row.collection == item.collection and row.number == item.number
            ]
        found[key] = ids[:1]
    return found
