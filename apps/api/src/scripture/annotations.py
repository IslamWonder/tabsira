"""
Import the annotated corpus' model-written annotations, for retrieval only (decision 16).

The corpus (`final_complete_verses_20251202_194512.json`, by Firas) gives every
verse an `arabic_annotation` written by gpt-4o-mini. Only its seven stable keys
are kept, joined to the stored verse by surah and ayah. The corpus' English
translation and any key outside the seven are never read, and its verse text
(`text_ar`) is read for one purpose only: some annotation strings repeat the
verse (the model echoed it), and every string that contains the whole verse,
once both are folded, is left out, as is any string containing the stored
quranpedia text of that verse. No annotation can then stand in for scripture.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import QuranAnnotation, QuranVerse, QuranVerseSearch
from src.scripture.errors import ScriptureError
from src.scripture.text import search_copy

ANNOTATIONS_FILE = "quran-annotations.json"
# The audited file (docs/ASSET_MANIFEST.md); another one needs its own audit first.
ANNOTATIONS_SHA256 = "2716625c1f383f332b96a0ab6f82d5942fa25990b3827c5ad493f6957b3c0700"
ANNOTATION_KEYS = (
    "islamic_cognitive_dimension",
    "related_sciences",
    "related_research_fields",
    "categories",
    "search_retrieval_fields",
    "semantic_tags_entities",
    "application_fields",
)
# The one misspelt domain value the audit found (299 records).
DOMAIN_SPELLINGS = {"qsas": "qasas"}


class AnnotationImportError(ScriptureError):
    """The annotated corpus does not fit the stored verses."""


@dataclass
class AnnotationsReport:
    verses: int
    echoes_left_out: int


def _strings(value: Any) -> list[str]:
    """Return a list of non-empty strings from a list, a lone string, or anything else."""
    items = value if isinstance(value, list) else [value]
    return [item.strip() for item in items if isinstance(item, str) and item.strip()]


def _section(annotation: dict[str, Any], key: str) -> dict[str, Any]:
    value = annotation.get(key)
    return value if isinstance(value, dict) else {}


class _EchoFilter:
    """Leave out every string that holds a whole verse, comparing folded words."""

    def __init__(self, verses: Iterable[str]) -> None:
        self.verses = [f" {folded} " for folded in verses if folded]
        self.left_out = 0

    def _echoes(self, value: str) -> bool:
        padded = f" {search_copy(value)} "
        return any(verse in padded for verse in self.verses)

    def clean(self, value: Any) -> Any:
        """Return `value` without its echoing strings; a dict loses the key, a list the item."""
        if isinstance(value, dict):
            kept = {key: self.clean(item) for key, item in value.items()}
            return {key: item for key, item in kept.items() if item is not _LEFT_OUT}
        if isinstance(value, list):
            return [item for item in (self.clean(item) for item in value) if item is not _LEFT_OUT]
        if isinstance(value, str) and self._echoes(value):
            self.left_out += 1
            return _LEFT_OUT
        return value


_LEFT_OUT = object()


def annotation_row(
    record: dict[str, Any], source_sha256: str, verses: Iterable[str]
) -> tuple[dict[str, Any], int]:
    """
    Return the database row of one corpus record and how many echoing strings it lost.

    `verses` are folded texts of the verse (the corpus' and the stored one).
    """
    echoes = _EchoFilter(verses)
    raw = record["arabic_annotation"]
    annotation = echoes.clean({key: raw[key] for key in ANNOTATION_KEYS if key in raw})
    domain = _section(annotation, "islamic_cognitive_dimension").get("islamic_domain")
    domain = domain.strip().lower() if isinstance(domain, str) and domain.strip() else None
    search = _section(annotation, "search_retrieval_fields")
    row = {
        "surah": int(record["surah_no"]),
        "ayah": int(record["ayah_no_surah"]),
        "source_ayah_id": int(record["ayah_id"]),
        "islamic_domain": DOMAIN_SPELLINGS.get(domain, domain) if domain else None,
        "categories": _strings(annotation.get("categories")),
        "key_concepts": _strings(search.get("key_concepts")),
        "keywords_ar": _strings(search.get("keywords_ar")),
        "semantic_tags": _strings(
            _section(annotation, "semantic_tags_entities").get("semantic_tags")
        ),
        "annotation": annotation,
        "annotation_model": record.get("annotation_model"),
        "source_sha256": source_sha256,
    }
    return row, echoes.left_out


def check_records(raw: Any) -> list[dict[str, Any]]:
    """Return the corpus records; a corpus that is not a list, or has a verse twice, is refused."""
    if not isinstance(raw, list):
        message = "the annotated corpus is not a list of verse records"
        raise AnnotationImportError(message)
    keys = [(int(record["surah_no"]), int(record["ayah_no_surah"])) for record in raw]
    if len(keys) != len(set(keys)):
        message = "the annotated corpus has a verse twice"
        raise AnnotationImportError(message)
    return raw


async def import_annotations(
    session: AsyncSession, raw: Any, source_sha256: str
) -> AnnotationsReport:
    """Replace every annotation with those of `raw`; each must annotate a stored verse."""
    records = check_records(raw)
    stored = {
        (surah, ayah): folded
        for surah, ayah, folded in await session.execute(
            select(QuranVerse.surah, QuranVerse.ayah, QuranVerseSearch.normalized_text).join(
                QuranVerseSearch, QuranVerseSearch.verse_id == QuranVerse.id
            )
        )
    }
    keys = {(int(r["surah_no"]), int(r["ayah_no_surah"])) for r in records}
    missing = sorted(keys - set(stored))
    if missing:
        sample = ", ".join(f"{surah}:{ayah}" for surah, ayah in missing[:5])
        message = f"{len(missing)} annotated verses are not in the store ({sample}); import the Quran first"
        raise AnnotationImportError(message)
    rows = []
    left_out = 0
    for record in records:
        key = (int(record["surah_no"]), int(record["ayah_no_surah"]))
        verses = (search_copy(record.get("text_ar") or ""), stored[key])
        row, dropped = annotation_row(record, source_sha256, verses)
        rows.append(row)
        left_out += dropped
    await session.execute(delete(QuranAnnotation))
    if rows:
        await session.execute(insert(QuranAnnotation), rows)
    return AnnotationsReport(verses=len(rows), echoes_left_out=left_out)
