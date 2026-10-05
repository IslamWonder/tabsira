"""
Read-only scripture: one verse, one hadith, exactly as stored, with what a reader needs to check it.

The text is returned byte for byte as stored, with its SHA-256, its source and
version, and the link where the reader can check it. A hadith also carries its
display spans (positions in the text, never a cut copy), the dataset's grades
marked informational, the editor-recorded dorar.net ruling and whether it is
eligible as evidence (decisions 18 and 58). Nothing here writes, and no model-written
field (annotations, Sunnah signals) is ever returned. Public: no account needed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.errors import AppError, ErrorCode
from src.models import (
    Hadith,
    HadithCollection,
    QuranSurah,
    QuranVerse,
    ScriptureSyncState,
)
from src.scripture.links import quranpedia_verse_url
from src.scripture.quran import SYNC_SOURCE
from src.scripture.quranpedia import MUSHAF_ID, SITE_URL
from src.scripture.rulings import eligible_given, latest_ruling
from src.scripture.spans import SpanRole, hadith_spans

router = APIRouter(prefix="/scripture", tags=["scripture"])

Session = Annotated[AsyncSession, Depends(get_db)]
# Where a text came from and how it was checked (master prompt §10). Every text
# here is a stored copy; none was fetched from its source for this request. A
# verse is quranpedia's own text, from its official dump checked against the
# SHA-256 quranpedia publishes and kept current by its changes feed (decision
# 16): verified, served from our copy. A hadith's text is the dataset's.
VerseStatus = Literal["verified_cached"]
CorpusStatus = Literal["local_corpus"]
MUSHAF_NAME = "مصحف حفص نسخة نصية"


class QuranSource(BaseModel):
    name: Literal["quranpedia.net"] = "quranpedia.net"
    url: str = SITE_URL
    mushaf_id: int = MUSHAF_ID
    mushaf_name: str = MUSHAF_NAME
    quranpedia_ayah_id: int
    version: str = Field(description="`dump:<dump version>` or `change:<time of the correction>`")
    dump_version: str | None
    last_sync_at: datetime | None


class QuranLinks(BaseModel):
    quranpedia: str


class QuranVerseOut(BaseModel):
    surah: int
    ayah: int
    surah_name: str
    text: str = Field(description="Exactly as stored; never normalised")
    sha256: str = Field(description="SHA-256 of the UTF-8 bytes of `text`")
    page: int
    juz: int
    source: QuranSource
    links: QuranLinks
    status: VerseStatus = "verified_cached"


class CollectionOut(BaseModel):
    slug: str
    name_ar: str
    source_dataset: str
    source_url: str
    licence: str
    version: str


class ChapterOut(BaseModel):
    book_number: int | None
    book_name: str | None
    number_in_book: int | None


class SpanOut(BaseModel):
    start: int
    end: int
    role: SpanRole


class GradeOut(BaseModel):
    name: str
    grade: str


class HadithOut(BaseModel):
    collection: CollectionOut
    number: str = Field(description="As the dataset numbers it")
    arabic_number: str | None
    chapter: ChapterOut | None
    text: str = Field(description="Exactly as stored, invisible direction marks included")
    sha256: str = Field(description="SHA-256 of the UTF-8 bytes of `text`")
    spans: list[SpanOut] = Field(
        description=(
            "Positions in `text`, counted in Unicode code points (not UTF-16 units); "
            "their slices join back into it"
        )
    )
    informational_grades: list[GradeOut] | None = Field(
        description="The dataset's grades as given; informational only, never decide eligibility"
    )
    status: CorpusStatus = "local_corpus"


def _not_found(what: str) -> AppError:
    return AppError(
        ErrorCode.NOT_FOUND, f"No {what} is stored.", status_code=status.HTTP_404_NOT_FOUND
    )


async def read_verse(session: AsyncSession, surah: int, ayah: int) -> QuranVerseOut | None:
    """Return a stored verse as the read API shows it, or None; shared with the insight pages."""
    row = (
        await session.execute(
            select(QuranVerse, QuranSurah.name_ar)
            .join(QuranSurah, QuranSurah.number == QuranVerse.surah)
            .where(QuranVerse.surah == surah, QuranVerse.ayah == ayah)
        )
    ).one_or_none()
    if row is None:
        return None
    verse, surah_name = row
    sync = await session.get(ScriptureSyncState, SYNC_SOURCE)
    return QuranVerseOut(
        surah=verse.surah,
        ayah=verse.ayah,
        surah_name=surah_name,
        text=verse.text,
        sha256=verse.text_sha256,
        page=verse.page,
        juz=verse.juz,
        source=QuranSource(
            quranpedia_ayah_id=verse.quranpedia_ayah_id,
            version=verse.source_version,
            dump_version=sync.dump_version if sync else None,
            last_sync_at=sync.last_success_at if sync else None,
        ),
        links=QuranLinks(quranpedia=quranpedia_verse_url(verse.surah, verse.quranpedia_ayah_id)),
    )


async def read_hadith(session: AsyncSession, collection: str, number: str) -> HadithOut | None:
    """
    Return a stored hadith as the read API shows it, or None; shared with the insight pages.

    None also for a hadith an editor ruled out (decision 65): it is never shown, and no
    ruling of any kind is displayed.
    """
    row = (
        await session.execute(
            select(Hadith, HadithCollection)
            .join(HadithCollection, HadithCollection.slug == Hadith.collection)
            .where(Hadith.collection == collection, Hadith.number == number)
        )
    ).one_or_none()
    if row is None:
        return None
    stored, book = row
    if not eligible_given(await latest_ruling(session, stored.id)):
        return None
    has_chapter = stored.book_number is not None
    return HadithOut(
        collection=CollectionOut(
            slug=book.slug,
            name_ar=book.name_ar,
            source_dataset=book.source_dataset,
            source_url=book.source_url,
            licence=book.licence,
            version=book.source_version,
        ),
        number=stored.number,
        arabic_number=stored.arabic_number,
        chapter=ChapterOut(
            book_number=stored.book_number,
            book_name=stored.book_name,
            number_in_book=stored.number_in_book,
        )
        if has_chapter
        else None,
        text=stored.text,
        sha256=stored.text_sha256,
        spans=[
            SpanOut(start=span.start, end=span.end, role=span.role)
            for span in hadith_spans(stored.text)
        ],
        informational_grades=(
            [GradeOut(**grade) for grade in stored.informational_grades]
            if stored.informational_grades is not None
            else None
        ),
    )


@router.get("/quran/{surah}/{ayah}", summary="One verse of the Quran")
async def quran_verse(
    session: Session,
    surah: Annotated[int, Path(ge=1, le=114)],
    ayah: Annotated[int, Path(ge=1, le=286)],
) -> QuranVerseOut:
    """Return a verse of quranpedia's mushaf 2 exactly as stored, with its hash and source."""
    verse = await read_verse(session, surah, ayah)
    if verse is None:
        what = f"verse {surah}:{ayah}"
        raise _not_found(what)
    return verse


@router.get("/hadith/{collection}/{number}", summary="One hadith")
async def hadith(
    session: Session,
    collection: Annotated[str, Path(pattern=r"^[a-z]{2,32}$")],
    number: Annotated[str, Path(pattern=r"^[0-9]{1,7}(\.[0-9]{1,3})?$")],
) -> HadithOut:
    """Return a hadith exactly as stored, with its spans, its ruling and its eligibility."""
    found = await read_hadith(session, collection, number)
    if found is None:
        what = f"hadith {collection} {number}"
        raise _not_found(what)
    return found
