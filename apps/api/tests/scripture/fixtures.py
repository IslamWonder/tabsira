"""
Real rows copied from the downloaded sources, for the scripture tests. Nothing here is typed by hand.

`tests/scripture/data/` holds:

- `quranpedia-mushafs-2.json`: quranpedia dump `mushafs-2.json.gz` (version 2026-10-03) with
  surahs 1 and 112 whole and a few verses of surahs 2 and 30, every field as in the dump.
- `quranpedia-surahs.json`: the same surahs from `surahs.json.gz`, five information fields kept.
- `quranpedia-changes.json`: `GET /v1/changes?since=2026-08-08`, three ayah rows kept.
- `quranpedia-ayah-2-30-50.json`: `GET /v1/mushafs/2/30/50`.
- `kfgqpc-v13-30-50.json`, `kfgqpc-v13-2-49.json`: verses 30:50 and 2:49 of fawazahmed0
  `ara-quranuthmanihaf` (King Fahd Complex text, version 13), real earlier encodings of the
  same verses.
- `ara-bukhari.json`, `ara-muslim.json`, `ara-abudawud.json`: a few hadiths of the
  fawazahmed0 hadith-api editions (commit df57907b), metadata trimmed to their sections.
- `musnad-ahmad.csv`, `sunan-al-darimi.csv`: the first two rows of the Open-Hadith-Data
  CSVs with diacritics (commit 1515f6cb).
- `quran-annotations.json`: seven whole records of the annotated corpus, schema drift included.
- `sunnah-enriched.json`: four records of `processed_sunnah_data.json`, still in their cp720
  mojibake, with the file's metadata.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import HadithSignal
from src.scripture.files import bytes_sha256
from src.scripture.guard import WritePurpose, allow_scripture_writes
from src.scripture.hadith import COLLECTIONS, CollectionSource, import_collection, parse_source
from src.scripture.quran import import_quran, parse_mushaf, parse_surahs

FIXTURES = Path(__file__).resolve().parent / "data"


def fixture_path(name: str) -> Path:
    return FIXTURES / name


def load_json(name: str) -> Any:
    return json.loads(fixture_path(name).read_text(encoding="utf-8"))


def verse_text(surah: int, ayah: int) -> str:
    """The text of a verse in the quranpedia fixture, as the dump gives it."""
    for entry in load_json("quranpedia-mushafs-2.json")["data"]["surahs"]:
        if entry["id"] == surah:
            for verse in entry["ayahs"]:
                if verse["number"] == ayah:
                    return str(verse["text"])
    raise KeyError((surah, ayah))


def hadith_text(book: str, number: float) -> str:
    """The text of a hadith in a fawazahmed0 fixture, as the edition gives it."""
    for entry in load_json(f"ara-{book}.json")["hadiths"]:
        if entry["hadithnumber"] == number:
            return str(entry["text"])
    raise KeyError((book, number))


async def store_quran(
    session: AsyncSession, *, earlier: Mapping[tuple[int, int], str] | None = None
) -> None:
    """Import the fixture mushaf as the importer does, some verses in another real encoding."""
    raw = copy.deepcopy(load_json("quranpedia-mushafs-2.json"))
    for surah in raw["data"]["surahs"]:
        for verse in surah["ayahs"]:
            if (surah["id"], verse["number"]) in (earlier or {}):
                verse["text"] = (earlier or {})[surah["id"], verse["number"]]
    await allow_scripture_writes(session, WritePurpose.IMPORT)
    await import_quran(
        session,
        parse_mushaf(raw),
        parse_surahs(load_json("quranpedia-surahs.json")),
        dump_sha256="0" * 64,
        source=str(fixture_path("quranpedia-mushafs-2.json")),
    )


# The books that have a fixture file, and that file.
HADITH_FIXTURES = {
    "bukhari": "ara-bukhari.json",
    "muslim": "ara-muslim.json",
    "abudawud": "ara-abudawud.json",
    "ahmad": "musnad-ahmad.csv",
    "darimi": "sunan-al-darimi.csv",
}


def fixture_sources() -> tuple[CollectionSource, ...]:
    """The real collection sources, pointed at the fixture files and their hashes."""
    return tuple(
        CollectionSource(
            source.slug,
            source.name_ar,
            source.display_order,
            source.format,
            source.remote_path,
            bytes_sha256(fixture_path(HADITH_FIXTURES[source.slug]).read_bytes()),
        )
        for source in COLLECTIONS
        if source.slug in HADITH_FIXTURES
    )


def cache_hadith_fixtures(cache_dir: Path) -> None:
    """Put every fixture hadith file where the importer looks for its source."""
    for source in fixture_sources():
        path = source.cache_path(cache_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(fixture_path(HADITH_FIXTURES[source.slug]).read_bytes())


async def store_hadiths(session: AsyncSession) -> None:
    """Import every fixture book as the importer does."""
    await allow_scripture_writes(session, WritePurpose.IMPORT)
    for source in fixture_sources():
        data = fixture_path(HADITH_FIXTURES[source.slug]).read_bytes()
        await import_collection(session, source, parse_source(source, data))


async def enrich_hadith(
    session: AsyncSession,
    hadith_id: int,
    record: str = "t1",
    *,
    coverage: float = 1.0,
    cited: bool = True,
) -> None:
    """Link a record of the enriched Sunnah file to a hadith, as the signals import does."""
    session.add(
        HadithSignal(
            source_record_id=record,
            hadith_id=hadith_id,
            match_coverage=coverage,
            matches=[{"hadith_id": hadith_id, "coverage": coverage, "cited": cited}],
            semantic_tags=[],
            key_concepts=[],
            topics_for_retrieval=[],
            sciences={},
            generated_by_model="test",
            source_sha256="0" * 64,
        )
    )
    await session.flush()
