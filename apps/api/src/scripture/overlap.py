"""
Does model text repeat any stored verse or hadith? The leak guard's check against the whole store.

The pattern detector catches quotation by its form (marks, brackets, an
introducer, vocalisation); the shingle detector catches words shared with the
texts an insight cites. This module catches the rest: a run of `WINDOW` words
of any verse or hadith in the store, copied without any mark, in the mushaf's
spelling or today's. Both sides are compared as guard skeletons
(`src.scripture.guard_fold`), kept in the search tables beside the search copy,
so the displayed text is never touched. The window is long enough that the stock
phrases every Arabic text shares do not count as a quotation.

Each run is matched as `%run%` on the folded column itself, so the trigram
index of the column serves it. The run is not held to word boundaries: a run
whose first or last word lost a letter glued to it (a conjunction, a pronoun)
is still the same quotation, and refusing it is the safe side. The skeleton
keeps letters and digits only, so no LIKE wildcard or escape can reach a
pattern from model text.

The runs go to the database as one array, each probed by its own index scan.
An `OR` of the runs in one condition looks cheaper to the planner as a
sequential scan, which on the 65,712 hadiths took about nine seconds an insight.

A verse shorter than the window («قل هو الله أحد», «إن مع العسر يسرا») holds no
run of seven words, so it is held against the text whole: the text's skeleton,
padded with a space on each side, contains the verse's padded skeleton. Whole
words only, since a short verse is a few words that prose may share in part.
Verses of three to six words qualify (about 1,700); one or two words are the
stock phrases of every Arabic text. The database keeps each verse's word count
(`guard_words`, computed and indexed), so the check reads those rows only.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import Select, Text, bindparam, func, literal, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import HadithSearch, QuranVerseSearch
from src.models.scripture import quran_verse_spans
from src.scripture.guard_fold import guard_fold

WINDOW = 7
# A verse of this many guard words is held against the text whole, by word.
SHORT_VERSE_WORDS = range(3, WINDOW)
# The guard skeletons compared, each with a trigram index: each verse, each verse with
# the six words after it in its surah (a quotation across short verses), each hadith.
COLUMNS = (
    QuranVerseSearch.guard_text,
    quran_verse_spans.c.guard_text,
    HadithSearch.guard_text,
)


def patterns(texts: Iterable[str], window: int = WINDOW) -> list[str]:
    """Return the LIKE patterns of every run of `window` skeleton words in `texts`."""
    found: set[str] = set()
    for text in texts:
        words = guard_fold(text).split()
        for start in range(len(words) - window + 1):
            found.add(f"%{' '.join(words[start : start + window])}%")
    return sorted(found)


def statements(wanted: list[str]) -> list[Select[int]]:
    """Return one query per folded column, finding a row that holds any of the `wanted` runs."""
    runs = (
        func.unnest(bindparam("runs", wanted, type_=ARRAY(Text)))
        .table_valued("run")
        .render_derived(name="wanted")
    )
    return [
        select(literal(1))
        .select_from(runs)
        .where(select(literal(1)).where(column.like(runs.c.run)).exists())
        .limit(1)
        for column in COLUMNS
    ]


def padded(texts: Iterable[str]) -> list[str]:
    """Return the skeleton of each of `texts` between spaces, for the whole-verse check."""
    return sorted({f" {folded} " for text in texts if (folded := guard_fold(text))})


def short_verse_statement(wanted: list[str]) -> Select[int]:
    """Return the query finding a verse of a few words that lies whole in any of the `wanted` texts."""
    written = (
        func.unnest(bindparam("texts", wanted, type_=ARRAY(Text)))
        .table_valued("text")
        .render_derived(name="written")
    )
    verse = literal(" ") + QuranVerseSearch.guard_text + literal(" ")
    short = QuranVerseSearch.guard_words.between(SHORT_VERSE_WORDS[0], SHORT_VERSE_WORDS[-1])
    return (
        select(literal(1))
        .select_from(written)
        .where(select(literal(1)).where(short, func.strpos(written.c.text, verse) > 0).exists())
        .limit(1)
    )


async def repeats_store(db: AsyncSession, texts: Iterable[str], window: int = WINDOW) -> bool:
    """
    Tell whether any of `texts` repeats a stored verse or hadith.

    A run of `window` words of any text of the store, or a verse shorter than
    the window quoted whole.
    """
    texts = list(texts)
    wanted = patterns(texts, window)
    for statement in statements(wanted) if wanted else []:
        if await db.scalar(statement) is not None:
            return True
    whole = padded(texts)
    return bool(whole) and await db.scalar(short_verse_statement(whole)) is not None
