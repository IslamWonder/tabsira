"""
The leak guard of the insight stages, with the scripture store as its corpus.

Every free text a model writes for an insight (the planner's fields, the
verifier's limits, the explanation parts and the small step, the clarification
question) goes through three checks, in the same shared fold the scan and the
chat guards use (`src.scripture.guard_fold`), so a quotation in today's
spelling is caught as surely as one in the mushaf's:

- the pattern rules of `src.pipeline.leak_guard`;
- a comparison, five words at a time, with every verse (its stored guard
  skeletons, in the mushaf's spelling and in today's) and with the hadiths that
  stage was shown. The honorific «صلى الله
  عليه وسلم» is left out of the hadith runs: an explanation may name the
  Prophet with it without quoting anyone;
- the whole store, seven words at a time (`src.scripture.overlap.repeats_store`):
  any verse, any run across short verses, any of the 65,712 hadiths.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import QuranVerseSearch, QuranVerseStandardGuard
from src.pipeline.leak_guard import (
    LeakDetector,
    LeakFinding,
    LeakGuard,
    LeakKind,
    LeakVerdict,
    PatternLeakDetector,
    ScriptureLeakError,
    ShingleOverlapDetector,
)
from src.scripture.guard_fold import guard_fold
from src.scripture.overlap import WINDOW, repeats_store

_HONORIFIC = guard_fold("صلى الله عليه وسلم")
STORE_FINDING = LeakFinding(
    kind=LeakKind.CORPUS_OVERLAP,
    detail=f"a run of {WINDOW} words of a stored verse or hadith",
)


def without_honorific(text: str) -> str:
    """Return the guard skeleton of `text` with the honorific taken out."""
    return f" {guard_fold(text)} ".replace(f" {_HONORIFIC} ", " ").strip()


async def quran_detector(session: AsyncSession) -> ShingleOverlapDetector:
    """
    Build the detector of runs of words shared with any verse (about 80,000 runs a spelling).

    Both skeletons of every verse, the mushaf's and today's (our conversion of the stored
    text, task 05.9): a run of five words in either spelling is a quotation.
    """
    texts = list(
        await session.scalars(
            select(QuranVerseSearch.guard_text).union_all(
                select(QuranVerseStandardGuard.guard_text)
            )
        )
    )
    # Seconds of pure Python: in a thread, so the event loop keeps serving meanwhile.
    return await asyncio.to_thread(lambda: ShingleOverlapDetector(skeletons=texts))


class EngineGuard:
    """The guard of one stage: patterns and shingles first, then the whole store."""

    def __init__(self, guard: LeakGuard, session: AsyncSession | None) -> None:
        self._guard = guard
        self._session = session

    async def refused(self, fields: Mapping[str, str]) -> dict[str, LeakVerdict]:
        """Return the verdict of every field whose text is refused, keyed by the field."""
        refused = {
            name: verdict
            for name, text in fields.items()
            if (verdict := self._guard.check(text)).leaked
        }
        rest = {name: text for name, text in fields.items() if name not in refused}
        if self._session is None or not await repeats_store(self._session, rest.values()):
            return refused
        # Rare: name the fields one by one only once the store has found a run.
        for name, text in rest.items():
            if await repeats_store(self._session, [text]):
                refused[name] = LeakVerdict(findings=[STORE_FINDING])
        return refused

    async def ensure_clean(self, fields: Mapping[str, str]) -> None:
        """Raise ScriptureLeakError naming every field whose text is refused."""
        refused = await self.refused(fields)
        if refused:
            raise ScriptureLeakError(refused)

    async def leaks(self, texts: Iterable[str]) -> bool:
        """Whether any of these texts looks like scripture or repeats the store."""
        return bool(await self.refused({str(index): text for index, text in enumerate(texts)}))


def scripture_guard(
    quran: LeakDetector | None,
    hadith_texts: Iterable[str] = (),
    session: AsyncSession | None = None,
) -> EngineGuard:
    """Return the guard for one stage: patterns, the Quran, the hadiths it was shown, the store."""
    detectors: list[LeakDetector] = [PatternLeakDetector()]
    if quran is not None:
        detectors.append(quran)
    shown: Sequence[str] = [without_honorific(text) for text in hadith_texts]
    if shown:
        detectors.append(ShingleOverlapDetector(skeletons=shown))
    return EngineGuard(LeakGuard(detectors), session)
