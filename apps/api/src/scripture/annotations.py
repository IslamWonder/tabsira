"""
Import the annotated corpus' model-written annotations, for retrieval only (decision 16).

The corpus (`final_complete_verses_20251202_194512.json`, by Firas) gives every
verse an `arabic_annotation` written by gpt-4o-mini. Only its seven stable keys
are kept, joined to the stored verse by surah and ayah. The corpus' own verse
text (`text_ar`), its English translation and any key outside the seven are
never read into the database, so no annotation can stand in for scripture.
Some annotation strings echo a verse; they stay inside the annotation, which
is never displayed.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import QuranAnnotation, QuranVerse
from src.scripture.errors import ScriptureError

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


def _strings(value: Any) -> list[str]:
    """Return a list of non-empty strings from a list, a lone string, or anything else."""
    items = value if isinstance(value, list) else [value]
    return [item.strip() for item in items if isinstance(item, str) and item.strip()]


def _section(annotation: dict[str, Any], key: str) -> dict[str, Any]:
    value = annotation.get(key)
    return value if isinstance(value, dict) else {}


def annotation_row(record: dict[str, Any], source_sha256: str) -> dict[str, Any]:
    """Return the database row of one corpus record: the seven keys and the fields retrieval queries."""
    raw = record["arabic_annotation"]
    annotation = {key: raw[key] for key in ANNOTATION_KEYS if key in raw}
    domain = _section(annotation, "islamic_cognitive_dimension").get("islamic_domain")
    domain = domain.strip().lower() if isinstance(domain, str) and domain.strip() else None
    search = _section(annotation, "search_retrieval_fields")
    return {
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


def parse_annotations(raw: Any, source_sha256: str) -> list[dict[str, Any]]:
    """Return one row per verse; a corpus with a verse twice is refused."""
    if not isinstance(raw, list):
        message = "the annotated corpus is not a list of verse records"
        raise AnnotationImportError(message)
    rows = [annotation_row(record, source_sha256) for record in raw]
    keys = [(row["surah"], row["ayah"]) for row in rows]
    if len(keys) != len(set(keys)):
        message = "the annotated corpus has a verse twice"
        raise AnnotationImportError(message)
    return rows


async def import_annotations(session: AsyncSession, rows: list[dict[str, Any]]) -> int:
    """Replace every annotation with `rows`; each must annotate a stored verse."""
    stored = {
        (surah, ayah)
        for surah, ayah in await session.execute(select(QuranVerse.surah, QuranVerse.ayah))
    }
    missing = sorted({(row["surah"], row["ayah"]) for row in rows} - stored)
    if missing:
        sample = ", ".join(f"{surah}:{ayah}" for surah, ayah in missing[:5])
        message = f"{len(missing)} annotated verses are not in the store ({sample}); import the Quran first"
        raise AnnotationImportError(message)
    await session.execute(delete(QuranAnnotation))
    if rows:
        await session.execute(insert(QuranAnnotation), rows)
    return len(rows)
