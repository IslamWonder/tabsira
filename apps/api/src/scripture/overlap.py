"""
Does model text repeat any stored verse or hadith? The leak guard's check against the whole store.

The pattern detector catches quotation by its form (marks, brackets, an
introducer, vocalisation); the shingle detector catches words shared with the
texts an insight cites. This module catches the rest: a run of `WINDOW` words
of any verse or hadith in the store, copied without any mark. Both sides are
compared in the folded search form (`search_copy`), on the search tables, so
the displayed text is never touched. The window is long enough that the stock
phrases every Arabic text shares do not count as a quotation.

Each run is matched as `%run%` on the folded column itself, so the trigram
index of the column serves it. The run is not held to word boundaries: a run
whose first or last word lost a letter glued to it (a conjunction, a pronoun)
is still the same quotation, and refusing it is the safe side. `search_copy`
keeps letters and digits only, so no LIKE wildcard or escape can reach a
pattern from model text.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import Select, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import HadithSearch, QuranVerseSearch
from src.scripture.text import search_copy

WINDOW = 7
# The folded columns compared, each with a trigram index.
COLUMNS = (QuranVerseSearch.normalized_text, HadithSearch.normalized_text)


def patterns(texts: Iterable[str], window: int = WINDOW) -> list[str]:
    """Return the LIKE patterns of every run of `window` folded words in `texts`."""
    found: set[str] = set()
    for text in texts:
        words = search_copy(text).split()
        for start in range(len(words) - window + 1):
            found.add(f"%{' '.join(words[start : start + window])}%")
    return sorted(found)


def statements(wanted: list[str]) -> list[Select[int]]:
    """Return one query per folded column, finding a row that holds any of the `wanted` runs."""
    return [
        select(literal(1)).where(or_(*(column.like(pattern) for pattern in wanted))).limit(1)
        for column in COLUMNS
    ]


async def repeats_store(db: AsyncSession, texts: Iterable[str], window: int = WINDOW) -> bool:
    """Tell whether any of `texts` repeats `window` words in a row of a stored verse or hadith."""
    wanted = patterns(texts, window)
    if not wanted:
        return False
    for statement in statements(wanted):
        if await db.scalar(statement) is not None:
            return True
    return False
