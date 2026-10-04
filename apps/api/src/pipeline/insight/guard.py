"""
The leak guard of the insight stages, with the scripture store as its corpus.

Every free text a model writes for an insight goes through the pattern rules
of `src.pipeline.leak_guard` and through a comparison, five words at a time,
with the whole Quran (its folded search copies) and with the hadiths that
stage was shown. The honorific «صلى الله عليه وسلم» is left out of the hadith
shingles: an explanation may name the Prophet with it without quoting anyone.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import QuranVerseSearch
from src.pipeline.leak_guard import (
    LeakDetector,
    LeakGuard,
    PatternLeakDetector,
    ShingleOverlapDetector,
    normalize_arabic,
)

_HONORIFIC = normalize_arabic("صلى الله عليه وسلم")


def without_honorific(text: str) -> str:
    """Return the comparison form of `text` with the honorific taken out."""
    return normalize_arabic(text).replace(_HONORIFIC, " ")


async def quran_detector(session: AsyncSession) -> ShingleOverlapDetector:
    """Build the detector of runs of words shared with any verse (about 80,000 runs)."""
    texts = await session.scalars(select(QuranVerseSearch.normalized_text))
    return ShingleOverlapDetector(texts)


def scripture_guard(quran: LeakDetector | None, hadith_texts: Iterable[str] = ()) -> LeakGuard:
    """Return the guard for one stage: patterns, the Quran, and the hadiths it was shown."""
    detectors: list[LeakDetector] = [PatternLeakDetector()]
    if quran is not None:
        detectors.append(quran)
    shown: Sequence[str] = [without_honorific(text) for text in hadith_texts]
    if shown:
        detectors.append(ShingleOverlapDetector(shown))
    return LeakGuard(detectors)
