"""
Real rows copied from the downloaded sources, for the scripture tests. Nothing here is typed by hand.

`tests/scripture/data/` holds:

- `quranpedia-mushafs-2.json`: quranpedia dump `mushafs-2.json.gz` (version 2026-10-03) with
  surahs 1 and 112 whole and a few verses of surahs 2 and 30, every field as in the dump.
- `quranpedia-surahs.json`: the same surahs from `surahs.json.gz`, five information fields kept.
- `quranpedia-changes.json`: `GET /v1/changes?since=2026-08-08`, three ayah rows kept.
- `quranpedia-ayah-2-30-50.json`: `GET /v1/mushafs/2/30/50`.
- `kfgqpc-v13-30-50.json`: verse 30:50 of fawazahmed0 `ara-quranuthmanihaf` (King Fahd
  Complex text, version 13), a real earlier encoding of the same verse.
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
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.scripture.files import bytes_sha256
from src.scripture.guard import WritePurpose, allow_scripture_writes
from src.scripture.hadith import COLLECTIONS, CollectionSource
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


async def store_quran(session: AsyncSession, *, text_30_50: str | None = None) -> None:
    """Import the fixture mushaf as the importer does, optionally with another real text of 30:50."""
    raw = copy.deepcopy(load_json("quranpedia-mushafs-2.json"))
    if text_30_50 is not None:
        for surah in raw["data"]["surahs"]:
            for verse in surah["ayahs"]:
                if (surah["id"], verse["number"]) == (30, 50):
                    verse["text"] = text_30_50
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
