"""
Import quranpedia's mushaf 2 and apply corrected verses.

Each verse is stored with its text exactly as the dump gives it, the SHA-256 of
that text, its quranpedia id and the dump version. A later dump or a change
from the feed that carries a different text replaces it through
`apply_correction`: the previous text goes to `quran_verse_history`, the new
one is stored with its own hash and version, and an audit row records both
hashes and where the new text came from. Nothing here edits a text.

Whenever a search copy is added or replaced, the verse spans the leak guard
reads across verses (`quran_verse_spans`) are rebuilt in the same transaction.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, insert, select, update
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    QuranSurah,
    QuranVerse,
    QuranVerseHistory,
    QuranVerseSearch,
    ScriptureAudit,
    ScriptureSyncState,
)
from src.models.scripture import quran_verse_spans
from src.scripture.errors import ScriptureError
from src.scripture.quranpedia import MUSHAF_ID
from src.scripture.text import search_copy, sha256_hex

SYNC_SOURCE = f"quranpedia:mushaf-{MUSHAF_ID}"
COMPLETE_SURAHS = 114
COMPLETE_VERSES = 6236
# The count of verses this mushaf follows: Hafs reads with the Kufan count.
KUFAN_COUNT_TITLE = "العد الكوفي"


class QuranImportError(ScriptureError):
    """The dump is not the one expected, or not whole."""


class DumpAyah(BaseModel):
    id: int
    number: int
    surah: int
    page_number: int
    juz: int
    text: str


class DumpSurah(BaseModel):
    id: int
    name: str
    ayahs: list[DumpAyah]


class MushafData(BaseModel):
    id: int
    name: str
    surahs: list[DumpSurah]


class DumpLicense(BaseModel):
    version: str


class MushafDump(BaseModel):
    """`mushafs-2.json.gz`: the licence block (with the dump version) and the mushaf."""

    model_config = ConfigDict(populate_by_name=True)

    license: DumpLicense
    schema_path: str = Field(alias="schema")
    data: MushafData

    @property
    def version(self) -> str:
        return self.license.version

    def verses(self) -> list[DumpAyah]:
        return [ayah for surah in self.data.surahs for ayah in surah.ayahs]

    def is_complete(self) -> bool:
        return len(self.data.surahs) == COMPLETE_SURAHS and len(self.verses()) == COMPLETE_VERSES


class InfoValue(BaseModel):
    value: str


class AyahCount(BaseModel):
    title: str
    value: int


class SurahInformation(BaseModel):
    surah_type: InfoValue
    words_count: InfoValue
    descent: InfoValue
    ayahs_count: list[AyahCount]

    def kufan_ayah_count(self) -> int:
        for count in self.ayahs_count:
            if count.title.strip() == KUFAN_COUNT_TITLE:
                return count.value
        message = "the surah information has no Kufan verse count"
        raise QuranImportError(message)


class SurahInfoEntry(BaseModel):
    surah: int
    information: SurahInformation


class SurahsDump(BaseModel):
    """`surahs.json.gz`: quranpedia's information about each surah."""

    license: DumpLicense
    data: list[SurahInfoEntry]


@dataclass
class QuranImportReport:
    version: str
    surahs: int = 0
    inserted: int = 0
    corrected: int = 0
    unchanged: int = 0
    metadata_updated: int = 0


def load_json_file(path: Path) -> Any:
    """Read a JSON file, gunzipping it when its name ends in .gz."""
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def parse_mushaf(raw: Any) -> MushafDump:
    """Validate the mushaf dump: mushaf 2 only, every verse once, under its own surah."""
    dump = MushafDump.model_validate(raw)
    if dump.data.id != MUSHAF_ID or dump.schema_path != f"/v1/mushafs/{MUSHAF_ID}":
        message = f"expected the dump of mushaf {MUSHAF_ID}, got mushaf {dump.data.id}"
        raise QuranImportError(message)
    seen: set[tuple[int, int]] = set()
    for surah in dump.data.surahs:
        for ayah in surah.ayahs:
            key = (ayah.surah, ayah.number)
            if ayah.surah != surah.id or key in seen or not ayah.text:
                message = f"verse {ayah.surah}:{ayah.number} is misplaced, repeated or empty"
                raise QuranImportError(message)
            seen.add(key)
    return dump


def parse_surahs(raw: Any) -> dict[int, SurahInformation]:
    return {entry.surah: entry.information for entry in SurahsDump.model_validate(raw).data}


def dump_tag(version: str) -> str:
    """Return the `source_version` of a text that came from the dump `version`."""
    return f"dump:{version}"


async def apply_correction(
    session: AsyncSession, verse: QuranVerse, text: str, version: str, source: str
) -> None:
    """Replace the text of `verse`, keeping the previous one in history and auditing both hashes."""
    previous = verse.text_sha256
    session.add(
        QuranVerseHistory(
            verse_id=verse.id,
            surah=verse.surah,
            ayah=verse.ayah,
            text=verse.text,
            text_sha256=verse.text_sha256,
            source_version=verse.source_version,
            imported_at=verse.imported_at,
            replaced_by_version=version,
        )
    )
    verse.text = text
    verse.text_sha256 = sha256_hex(text)
    verse.source_version = version
    verse.imported_at = datetime.now(UTC)
    await session.execute(
        update(QuranVerseSearch)
        .where(QuranVerseSearch.verse_id == verse.id)
        .values(normalized_text=search_copy(text))
    )
    await refresh_verse_spans(session)
    session.add(
        ScriptureAudit(
            entity="quran_verse",
            entity_key=f"{verse.surah}:{verse.ayah}",
            action="correct",
            old_sha256=previous,
            new_sha256=verse.text_sha256,
            source=source,
        )
    )
    await session.flush()


async def _upsert_surahs(
    session: AsyncSession, dump: MushafDump, info: dict[int, SurahInformation]
) -> int:
    rows = []
    for surah in dump.data.surahs:
        if surah.id not in info:
            message = f"the surah information has no entry for surah {surah.id}"
            raise QuranImportError(message)
        facts = info[surah.id]
        rows.append(
            {
                "number": surah.id,
                "name_ar": surah.name,
                "revelation_place": facts.surah_type.value.strip(),
                "revelation_order": int(facts.descent.value),
                "ayah_count": facts.kufan_ayah_count(),
                "words_count": int(facts.words_count.value),
                "source_version": dump_tag(dump.version),
            }
        )
    statement = pg_insert(QuranSurah).values(rows)
    columns = ("name_ar", "revelation_place", "revelation_order", "ayah_count", "words_count")
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[QuranSurah.number],
            set_={name: statement.excluded[name] for name in (*columns, "source_version")},
        )
    )
    return len(rows)


async def _record_sync_baseline(session: AsyncSession, version: str) -> None:
    """Start the changes feed from this dump, unless a sync has already gone further."""
    try:
        baseline = date.fromisoformat(version)
    except ValueError:
        message = f"the dump version {version!r} is not a date"
        raise QuranImportError(message) from None
    statement = pg_insert(ScriptureSyncState).values(
        source=SYNC_SOURCE, synced_through=baseline, dump_version=version
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[ScriptureSyncState.source],
            set_={
                "dump_version": statement.excluded.dump_version,
                "synced_through": func.greatest(
                    ScriptureSyncState.synced_through, statement.excluded.synced_through
                ),
            },
        )
    )


async def reconcile_verses(
    session: AsyncSession, dump: MushafDump, source: str, report: QuranImportReport
) -> None:
    """Insert new verses, correct changed ones and refresh their page facts; texts never edited."""
    existing = {
        (verse.surah, verse.ayah): verse for verse in (await session.scalars(select(QuranVerse)))
    }
    tag = dump_tag(dump.version)
    new_rows: list[dict[str, Any]] = []
    for ayah in dump.verses():
        verse = existing.get((ayah.surah, ayah.number))
        facts = {"quranpedia_ayah_id": ayah.id, "page": ayah.page_number, "juz": ayah.juz}
        if verse is None:
            new_rows.append(
                {
                    "surah": ayah.surah,
                    "ayah": ayah.number,
                    "mushaf_id": MUSHAF_ID,
                    "text": ayah.text,
                    "text_sha256": sha256_hex(ayah.text),
                    "source_version": tag,
                    **facts,
                }
            )
            continue
        if verse.text_sha256 != sha256_hex(ayah.text):
            await apply_correction(session, verse, ayah.text, tag, source)
            report.corrected += 1
        elif any(getattr(verse, name) != value for name, value in facts.items()):
            report.metadata_updated += 1
        else:
            report.unchanged += 1
        for name, value in facts.items():
            setattr(verse, name, value)
    await session.flush()
    if new_rows:
        inserted = await session.execute(
            insert(QuranVerse).returning(QuranVerse.id, QuranVerse.text), new_rows
        )
        await session.execute(
            insert(QuranVerseSearch),
            [
                {"verse_id": verse_id, "normalized_text": search_copy(text)}
                for verse_id, text in inserted
            ],
        )
        await refresh_verse_spans(session)
    report.inserted = len(new_rows)


async def refresh_verse_spans(session: AsyncSession) -> None:
    """Rebuild the folded verse spans from the search copies (a few thousand short rows)."""
    spans = f"{quran_verse_spans.schema}.{quran_verse_spans.name}"
    await session.execute(sa_text(f"REFRESH MATERIALIZED VIEW {spans}"))


async def import_quran(
    session: AsyncSession,
    dump: MushafDump,
    surahs: dict[int, SurahInformation],
    *,
    dump_sha256: str,
    source: str,
) -> QuranImportReport:
    """
    Bring the database to this dump; run inside a transaction with the import guard open.

    Running it again with the same dump changes nothing but the audit log.
    """
    report = QuranImportReport(version=dump.version)
    report.surahs = await _upsert_surahs(session, dump, surahs)
    await reconcile_verses(session, dump, source, report)
    session.add(
        ScriptureAudit(
            entity="quran_import",
            entity_key=f"mushaf-{MUSHAF_ID} {dump.version}",
            action="import",
            new_sha256=dump_sha256,
            source=source,
        )
    )
    await _record_sync_baseline(session, dump.version)
    await session.flush()
    return report
