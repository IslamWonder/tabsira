"""
Real rows copied from the downloaded sources, for the scripture tests. Nothing here is typed by hand.

`tests/fixtures/scripture/` holds:

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

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "scripture"


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
