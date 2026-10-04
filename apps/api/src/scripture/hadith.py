"""
The nine books (decision 17), each from a pinned commit of its dataset, verified by SHA-256.

Seven books come from the Arabic editions of fawazahmed0 `hadith-api`
(Unlicense); Musnad Ahmad and Sunan al-Darimi, which that dataset lacks, come
from mhashim6 `Open-Hadith-Data` (ODbL 1.0), its CSV files with diacritics.
Each hadith is stored with the number its dataset gives it, kept as text
(«402.2» stays «402.2»), its text exactly as given, invisible right-to-left
marks included, and the SHA-256 of that text. The dataset's grades are kept as
informational only. A record whose text is empty is not stored: there is
nothing to show, and its number is reported as skipped.

A stored hadith is never overwritten. A source whose text for a stored number
changed is refused, because the pinned commit and file hash say the text cannot
have changed; a new source version is a reviewed code change.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Hadith, HadithCollection, HadithSearch, ScriptureAudit
from src.scripture.errors import ScriptureError
from src.scripture.files import check_bytes, is_verified, write_atomically
from src.scripture.text import search_copy, sha256_hex

FAWAZ_DATASET = "fawazahmed0/hadith-api"
FAWAZ_COMMIT = "df57907be35291c91ad6a6691180e22ca9920784"
FAWAZ_LICENCE = "Unlicense"
OPEN_HADITH_DATASET = "mhashim6/Open-Hadith-Data"
OPEN_HADITH_COMMIT = "1515f6cba21efed20d8916bf55acef1dffa0d2d5"
OPEN_HADITH_LICENCE = "ODbL-1.0"


class SourceFormat(StrEnum):
    FAWAZ_JSON = "fawazahmed0-json"
    OPEN_HADITH_CSV = "open-hadith-data-csv"


class HadithImportError(ScriptureError):
    """A hadith source is malformed, unreachable, or would change a stored hadith."""


@dataclass(frozen=True)
class CollectionSource:
    """One book: where its pinned file lives, what it must hash to, how to read it."""

    slug: str
    name_ar: str
    display_order: int
    format: SourceFormat
    remote_path: str
    sha256: str

    @property
    def dataset(self) -> str:
        return FAWAZ_DATASET if self.format is SourceFormat.FAWAZ_JSON else OPEN_HADITH_DATASET

    @property
    def commit(self) -> str:
        return FAWAZ_COMMIT if self.format is SourceFormat.FAWAZ_JSON else OPEN_HADITH_COMMIT

    @property
    def licence(self) -> str:
        return FAWAZ_LICENCE if self.format is SourceFormat.FAWAZ_JSON else OPEN_HADITH_LICENCE

    @property
    def url(self) -> str:
        if self.format is SourceFormat.FAWAZ_JSON:
            return f"https://cdn.jsdelivr.net/gh/{FAWAZ_DATASET}@{self.commit}/{self.remote_path}"
        return f"https://raw.githubusercontent.com/{OPEN_HADITH_DATASET}/{self.commit}/{self.remote_path}"

    def cache_path(self, cache_dir: Path) -> Path:
        name = Path(self.remote_path).name
        if self.format is SourceFormat.FAWAZ_JSON:
            return cache_dir / "hadith" / name
        return cache_dir / "hadith" / "open-hadith-data" / name


def _fawaz(slug: str, name_ar: str, order: int, sha256: str) -> CollectionSource:
    return CollectionSource(
        slug, name_ar, order, SourceFormat.FAWAZ_JSON, f"editions/ara-{slug}.json", sha256
    )


COLLECTIONS: tuple[CollectionSource, ...] = (
    _fawaz(
        "bukhari",
        "صحيح البخاري",
        1,
        "e34a3402889ca378871da3c5984b7875c680920e93f1c8738ac7afe502179562",
    ),
    _fawaz(
        "muslim", "صحيح مسلم", 2, "194073b24090c5368e4d14a3f55c9e0ef144c7437bd7e5aa83aa4d2bc54a8ea0"
    ),
    _fawaz(
        "abudawud",
        "سنن أبي داود",
        3,
        "216139c5f40a8147e700d62ffa3b5b2fe45d0e034f86941a193c598c10056189",
    ),
    _fawaz(
        "tirmidhi",
        "جامع الترمذي",
        4,
        "408028cd56329ed78edbe3ad443beb96b58e16c3e5bd49f9bc7b0eac77c8820f",
    ),
    _fawaz(
        "nasai",
        "سنن النسائي",
        5,
        "c705983c19bb089c87cd6531aff609bd94d862183ed0859115b0ff991826a956",
    ),
    _fawaz(
        "ibnmajah",
        "سنن ابن ماجه",
        6,
        "b406e6be81588ab0ec1ddbed32f5fd95bbcdda242c460d88331e82eb5c2bc0aa",
    ),
    _fawaz(
        "malik", "موطأ مالك", 7, "088b1f354e110211da006d47e37dd8f8837368f318ed683271f0fdb0f09a3ab5"
    ),
    CollectionSource(
        "ahmad",
        "مسند أحمد",
        8,
        SourceFormat.OPEN_HADITH_CSV,
        "Musnad_Ahmad_Ibn-Hanbal/musnad_ahmad_ibn-hanbal_ahadith_mushakkala.utf8.csv",
        "41553fee47fe582a8d0b60fbea1f71b867df44d40adac94dcfe742571a8bce24",
    ),
    CollectionSource(
        "darimi",
        "سنن الدارمي",
        9,
        SourceFormat.OPEN_HADITH_CSV,
        "Sunan_Al-Darimi/sunan_al-darimi_ahadith_mushakkala_mufassala.utf8.csv",
        "bb995abb07a513cf76743e9580787e80c7ce5bd08dd6108c13e01d936a048327",
    ),
)


@dataclass(frozen=True)
class HadithRecord:
    number: str
    text: str
    arabic_number: str | None = None
    book_number: int | None = None
    book_name: str | None = None
    number_in_book: int | None = None
    grades: list[dict[str, str]] | None = None


@dataclass
class ParsedSource:
    records: list[HadithRecord]
    skipped_empty: list[str]


@dataclass
class CollectionReport:
    slug: str
    inserted: int
    unchanged: int
    skipped_empty: int


def _optional_number(value: Any) -> str | None:
    return None if value is None or str(value).strip() == "" else str(value)


def parse_fawaz(data: bytes) -> ParsedSource:
    """Read a fawazahmed0 edition; numbers stay as written in the file."""
    raw = json.loads(data, parse_float=str, parse_int=str)
    sections: dict[str, str] = raw["metadata"]["sections"]
    parsed = ParsedSource([], [])
    for item in raw["hadiths"]:
        number = str(item["hadithnumber"])
        if not item["text"].strip():
            parsed.skipped_empty.append(number)
            continue
        book = str(item["reference"]["book"])
        parsed.records.append(
            HadithRecord(
                number=number,
                text=item["text"],
                arabic_number=_optional_number(item.get("arabicnumber")),
                book_number=int(book),
                book_name=sections.get(book) or None,
                number_in_book=int(item["reference"]["hadith"]),
                grades=item["grades"],
            )
        )
    return parsed


def parse_open_hadith_csv(data: bytes) -> ParsedSource:
    """Read an Open-Hadith-Data file: rows of number and text, no header, no grades."""
    parsed = ParsedSource([], [])
    for row in csv.reader(io.StringIO(data.decode("utf-8"), newline="")):
        if len(row) != 2 or not row[0].isdigit():
            message = f"unexpected Open-Hadith-Data row starting {row[:1]!r}"
            raise HadithImportError(message)
        if not row[1].strip():
            parsed.skipped_empty.append(row[0])
            continue
        parsed.records.append(HadithRecord(number=row[0], text=row[1]))
    return parsed


def parse_source(source: CollectionSource, data: bytes) -> ParsedSource:
    parsed = (
        parse_fawaz(data)
        if source.format is SourceFormat.FAWAZ_JSON
        else parse_open_hadith_csv(data)
    )
    numbers = [record.number for record in parsed.records]
    if len(numbers) != len(set(numbers)):
        message = f"{source.slug}: the source numbers two hadiths alike"
        raise HadithImportError(message)
    return parsed


async def ensure_source_file(
    http: httpx.AsyncClient, cache_dir: Path, source: CollectionSource
) -> Path:
    """Return the cached file of `source`, downloading it from its pinned commit when missing."""
    path = source.cache_path(cache_dir)
    if is_verified(path, source.sha256):
        return path
    try:
        response = await http.get(source.url)
    except httpx.HTTPError as error:
        message = f"GET {source.url} failed: {type(error).__name__}"
        raise HadithImportError(message) from error
    if response.status_code != httpx.codes.OK:
        message = f"GET {source.url} answered {response.status_code}"
        raise HadithImportError(message)
    return write_atomically(path, check_bytes(response.content, source.sha256, path.name))


async def _upsert_collection(session: AsyncSession, source: CollectionSource) -> None:
    values = {
        "slug": source.slug,
        "name_ar": source.name_ar,
        "source_dataset": source.dataset,
        "source_url": source.url,
        "licence": source.licence,
        "source_version": source.commit,
        "source_file": source.remote_path,
        "source_sha256": source.sha256,
        "display_order": source.display_order,
    }
    statement = pg_insert(HadithCollection).values(values)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[HadithCollection.slug],
            set_={name: statement.excluded[name] for name in values if name != "slug"},
        )
    )


async def import_collection(
    session: AsyncSession, source: CollectionSource, parsed: ParsedSource
) -> CollectionReport:
    """Store the hadiths of one book not stored yet; run with the import guard open."""
    await _upsert_collection(session, source)
    result = await session.execute(
        select(Hadith.number, Hadith.text_sha256).where(Hadith.collection == source.slug)
    )
    stored = {row.number: row.text_sha256 for row in result}
    changed = [
        record.number
        for record in parsed.records
        if record.number in stored and stored[record.number] != sha256_hex(record.text)
    ]
    if changed:
        message = f"{source.slug}: the source changes stored hadiths ({', '.join(changed[:5])})"
        raise HadithImportError(message)
    new = [record for record in parsed.records if record.number not in stored]
    if new:
        inserted = await session.execute(
            insert(Hadith).returning(Hadith.id, Hadith.text),
            [
                {
                    "collection": source.slug,
                    "number": record.number,
                    "arabic_number": record.arabic_number,
                    "book_number": record.book_number,
                    "book_name": record.book_name,
                    "number_in_book": record.number_in_book,
                    "text": record.text,
                    "text_sha256": sha256_hex(record.text),
                    "informational_grades": record.grades,
                    "source_dataset": source.dataset,
                    "source_version": source.commit,
                }
                for record in new
            ],
        )
        await session.execute(
            insert(HadithSearch),
            [
                {"hadith_id": hadith_id, "normalized_text": search_copy(text)}
                for hadith_id, text in inserted
            ],
        )
    session.add(
        ScriptureAudit(
            entity="hadith_import",
            entity_key=f"{source.slug} {source.commit}",
            action="import",
            new_sha256=source.sha256,
            source=source.url,
        )
    )
    await session.flush()
    return CollectionReport(
        slug=source.slug,
        inserted=len(new),
        unchanged=len(parsed.records) - len(new),
        skipped_empty=len(parsed.skipped_empty),
    )
