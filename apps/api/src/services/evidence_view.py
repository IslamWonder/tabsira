"""
Scripture in a response: always read from the store by reference, never copied.

A publication holds references only (surah and ayah, collection and number). When a post is
shown, the text is read from the scripture store here, byte for byte as stored, with its
stored hash, and goes out as it is: no step normalises, shortens or rewrites it. A hadith is
shown as stored, with no ruling displayed (decision 65); only one an editor ruled out is left
out, and the post then shows what is left of its evidence, the verse alone. A reference the
store no longer holds is left out, never replaced by anything.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import or_, select, tuple_
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.scripture import Hadith, HadithCollection, HadithRuling, QuranSurah, QuranVerse
from src.schemas.social import HadithEvidenceOut, QuranEvidenceOut
from src.scripture.links import quranpedia_verse_url
from src.scripture.rulings import eligible_given

type QuranKey = tuple[int, int]
type HadithKey = tuple[str, str]


@dataclass
class Evidence:
    """The stored scripture a set of references resolves to."""

    quran: dict[QuranKey, QuranEvidenceOut] = field(default_factory=dict)
    hadith: dict[HadithKey, HadithEvidenceOut] = field(default_factory=dict)


async def _verses(db: AsyncSession, keys: set[QuranKey]) -> dict[QuranKey, QuranEvidenceOut]:
    if not keys:
        return {}
    rows = await db.execute(
        select(QuranVerse, QuranSurah.name_ar)
        .join(QuranSurah, QuranSurah.number == QuranVerse.surah)
        .where(tuple_(QuranVerse.surah, QuranVerse.ayah).in_(sorted(keys)))
    )
    return {
        (verse.surah, verse.ayah): QuranEvidenceOut(
            surah=verse.surah,
            ayah=verse.ayah,
            surah_name=surah_name,
            text=verse.text,
            sha256=verse.text_sha256,
            source_url=quranpedia_verse_url(verse.surah, verse.quranpedia_ayah_id),
        )
        for verse, surah_name in rows
    }


async def _hadiths(db: AsyncSession, keys: set[HadithKey]) -> dict[HadithKey, HadithEvidenceOut]:
    if not keys:
        return {}
    rows = (
        await db.execute(
            select(Hadith, HadithCollection.name_ar)
            .join(HadithCollection, HadithCollection.slug == Hadith.collection)
            .where(or_(*[(Hadith.collection == c) & (Hadith.number == n) for c, n in sorted(keys)]))
        )
    ).all()
    if not rows:
        return {}
    # The ruling in force is the last one recorded, one per hadith.
    rulings = {
        ruling.hadith_id: ruling
        for ruling in await db.scalars(
            select(HadithRuling)
            .where(HadithRuling.hadith_id.in_([hadith.id for hadith, _ in rows]))
            .order_by(
                HadithRuling.hadith_id, HadithRuling.recorded_at.desc(), HadithRuling.id.desc()
            )
            .ext(distinct_on(HadithRuling.hadith_id))
        )
    }
    shown: dict[HadithKey, HadithEvidenceOut] = {}
    for hadith, collection_name in rows:
        if not eligible_given(rulings.get(hadith.id)):
            continue
        shown[(hadith.collection, hadith.number)] = HadithEvidenceOut(
            collection=hadith.collection,
            collection_name=collection_name,
            number=hadith.number,
            text=hadith.text,
            sha256=hadith.text_sha256,
        )
    return shown


async def load_evidence(
    db: AsyncSession, quran: Iterable[QuranKey], hadith: Iterable[HadithKey]
) -> Evidence:
    """Read the verses and the eligible hadiths these references name, in two queries and a ruling lookup."""
    return Evidence(quran=await _verses(db, set(quran)), hadith=await _hadiths(db, set(hadith)))
