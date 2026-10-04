"""
The enriched Sunnah file: model-written ranking signals, linked to stored hadiths by text match.

`processed_sunnah_data.json` is UTF-8 that was once decoded as cp720 and saved
again. Every string is repaired with `s.encode("cp720").decode("utf-8")` and
the repair is proved lossless string by string (re-encoding gives back the
original). Its records were written by a language model from an abridged
hadith compilation; they are ranking signals only (master prompt §9).

Each record is linked to the stored hadiths its narration matches: the
narration is cut to its main text (no compiler code, no variant, no reference
or footnote), folded like the search copies, and scored against every hadith
by the IDF-weighted share of its word 3-grams the hadith contains. A hadith
that covers at least half is a match. Each book keeps its best match; a book
the compiler cites («[خ 8، م 16]») ranks before one it does not, then the
higher coverage; the first is the link. The folded
copies serve the matching only. The record's own narration is not stored, and
its `summary` and `modern_rephrase` are stored under names that say a model
wrote them; neither is ever shown as hadith text.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Hadith, HadithCollection, HadithSearch, HadithSignal
from src.scripture.errors import ScriptureError
from src.scripture.text import search_copy

SUNNAH_FILE = "sunnah-enriched.json"
# The audited file (docs/ASSET_MANIFEST.md §4); another one needs its own audit first.
SUNNAH_SHA256 = "b68a7f5f25bc7f512b28cf1ca4a7f5c1bd63641729158870784a7fefa8cc086c"
MATCH_THRESHOLD = 0.5
# A 3-gram found in more hadiths than this is isnad boilerplate: it still weighs
# in every score, but it does not make a hadith a candidate on its own.
CANDIDATE_MAX_DF = 2000

Gram = tuple[str, str, str]

_LEADING_CODE = re.compile(r"^\s*\(([^)]{1,8})\)\s*")
_VARIANT = re.compile("!|" + "وفي رواية")
_REFERENCES = re.compile(r"\[[^\]]*\]")
_FOOTNOTES = re.compile(r"\(\d+\)")
# The compiler's book codes, as in «[خ 8، م 16]»: a code, then the number in that book.
CITED_BOOKS = {
    "خ": "bukhari",
    "م": "muslim",
    "د": "abudawud",
    "ت": "tirmidhi",
    "ن": "nasai",
    "جه": "ibnmajah",
    "ط": "malik",
    "حم": "ahmad",
    "مي": "darimi",
}
# «(ق)», agreed upon: in both Sahihs.
AGREED_UPON = "ق"
TATWEEL = chr(0x0640)
_CITATION = re.compile(
    r"(?<![ء-ي])(" + "|".join(sorted(CITED_BOOKS, key=len, reverse=True)) + r")\s*\d"
)


class SunnahImportError(ScriptureError):
    """The enriched file is not the cp720 mojibake it is known to be, or is malformed."""


def repair_text(value: str) -> str:
    """Undo the cp720 mojibake of one string and prove the repair lossless."""
    try:
        repaired = value.encode("cp720").decode("utf-8")
    except UnicodeError:
        message = f"a string of the enriched file is not cp720 mojibake: {value[:20]!r}"
        raise SunnahImportError(message) from None
    require_round_trip(value, repaired)
    return repaired


def require_round_trip(original: str, repaired: str) -> None:
    """Refuse a repair unless re-encoding it gives back the original string exactly."""
    if repaired.encode("utf-8").decode("cp720", errors="replace") != original:
        message = f"the repair of {original[:20]!r} is not lossless"
        raise SunnahImportError(message)


def repair(value: Any) -> Any:
    """Repair every string inside `value`; keys are ASCII and stay as they are."""
    if isinstance(value, str):
        return repair_text(value)
    if isinstance(value, list):
        return [repair(item) for item in value]
    if isinstance(value, dict):
        return {key: repair(item) for key, item in value.items()}
    return value


def main_narration(original: str) -> str:
    """Return the record's main narration: no leading code, variant, reference or footnote."""
    text = _LEADING_CODE.sub("", original, count=1)
    text = _VARIANT.split(text, maxsplit=1)[0]
    text = _REFERENCES.sub(" ", text)
    return _FOOTNOTES.sub(" ", text)


def cited_collections(original: str) -> set[str]:
    """Return the books the compiler cites for a record, from its leading code and references."""
    cited = {
        CITED_BOOKS[code]
        for reference in _REFERENCES.findall(original)
        for code in _CITATION.findall(reference)
    }
    leading = _LEADING_CODE.match(original)
    for token in leading.group(1).replace(TATWEEL, "").split() if leading else ():
        if token == AGREED_UPON:
            cited |= {"bukhari", "muslim"}
        elif token in CITED_BOOKS:
            cited.add(CITED_BOOKS[token])
    return cited


def trigrams(folded: str) -> set[Gram]:
    words = folded.split()
    return {(words[i], words[i + 1], words[i + 2]) for i in range(len(words) - 2)}


class TrigramMatcher:
    """Score documents by the IDF-weighted share of a query's word 3-grams they contain."""

    def __init__(self, queries: dict[str, set[Gram]]) -> None:
        self.queries = queries
        self.vocabulary: set[Gram] = set().union(*queries.values())
        self.documents: dict[int, frozenset[Gram]] = {}
        self.postings: dict[Gram, list[int]] = defaultdict(list)

    def add(self, document_id: int, folded_text: str) -> None:
        grams = frozenset(trigrams(folded_text) & self.vocabulary)
        self.documents[document_id] = grams
        for gram in grams:
            self.postings[gram].append(document_id)

    def _idf(self, gram: Gram) -> float:
        total = len(self.documents)
        return math.log((total + 1) / (len(self.postings.get(gram, ())) + 1)) + 1

    def match(self, query_id: str, threshold: float) -> list[tuple[int, float]]:
        """Return (document, coverage) for every document covering at least `threshold`."""
        grams = self.queries[query_id]
        weights = {gram: self._idf(gram) for gram in grams}
        total = sum(weights.values())
        candidates = {
            document
            for gram in grams
            if 0 < len(self.postings.get(gram, ())) <= CANDIDATE_MAX_DF
            for document in self.postings[gram]
        }
        scored = (
            (document, sum(w for g, w in weights.items() if g in self.documents[document]) / total)
            for document in candidates
        )
        return sorted(
            ((document, coverage) for document, coverage in scored if coverage >= threshold),
            key=lambda pair: (-pair[1], pair[0]),
        )


@dataclass
class SignalsReport:
    records: int = 0
    linked: int = 0


def _strings(value: Any) -> list[str]:
    items = value if isinstance(value, list) else [value]
    return [item.strip() for item in items if isinstance(item, str) and item.strip()]


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


async def _hadith_corpus(session: AsyncSession) -> list[tuple[int, str, str, int, str]]:
    rows = await session.execute(
        select(
            Hadith.id,
            Hadith.collection,
            Hadith.number,
            HadithCollection.display_order,
            HadithSearch.normalized_text,
        )
        .join(HadithSearch, HadithSearch.hadith_id == Hadith.id)
        .join(HadithCollection, HadithCollection.slug == Hadith.collection)
    )
    return [(row[0], row[1], row[2], row[3], row[4]) for row in rows]


def _best_per_collection(
    found: list[tuple[int, float]], about: dict[int, tuple[str, str, int]], cited: set[str]
) -> list[dict[str, Any]]:
    """Keep each book's best match; a book the compiler cites comes before one it does not."""
    best: dict[str, dict[str, Any]] = {}
    for hadith_id, coverage in found:
        collection, number, order = about[hadith_id]
        if collection not in best:
            best[collection] = {
                "hadith_id": hadith_id,
                "collection": collection,
                "number": number,
                "coverage": round(coverage, 3),
                "_order": order,
            }
    ranked = sorted(
        best.values(),
        key=lambda m: (m["collection"] not in cited, -m["coverage"], m["_order"]),
    )
    return [{key: value for key, value in m.items() if key != "_order"} for m in ranked]


async def import_signals(
    session: AsyncSession, records: list[dict[str, Any]], *, model: str, source_sha256: str
) -> SignalsReport:
    """Replace every signal row with the repaired `records`, each linked to its best match."""
    queries = {
        str(record["id"]): trigrams(search_copy(main_narration(record.get("original_text") or "")))
        for record in records
    }
    if len(queries) != len(records):
        message = "the enriched file has a record id twice"
        raise SunnahImportError(message)
    matcher = TrigramMatcher(queries)
    about: dict[int, tuple[str, str, int]] = {}
    for hadith_id, collection, number, order, folded in await _hadith_corpus(session):
        matcher.add(hadith_id, folded)
        about[hadith_id] = (collection, number, order)

    rows = []
    report = SignalsReport(records=len(records))
    for record in records:
        matches = _best_per_collection(
            matcher.match(str(record["id"]), MATCH_THRESHOLD),
            about,
            cited_collections(record.get("original_text") or ""),
        )
        report.linked += bool(matches)
        rows.append(
            {
                "source_record_id": str(record["id"]),
                "hadith_id": matches[0]["hadith_id"] if matches else None,
                "match_coverage": matches[0]["coverage"] if matches else None,
                "matches": matches,
                "domain": _text(record.get("domain")),
                "category_old": _text(record.get("category_old")),
                "category_new": _text(record.get("category_new")),
                "subcategory": _text(record.get("subcategory")),
                "semantic_tags": _strings(record.get("semantic_tags")),
                "key_concepts": _strings(record.get("key_concepts")),
                "topics_for_retrieval": _strings(record.get("topics_for_retrieval")),
                "sciences": record["sciences"] if isinstance(record.get("sciences"), dict) else {},
                "model_written_summary": _text(record.get("summary")),
                "model_written_rephrase": _text(record.get("modern_rephrase")),
                "generated_by_model": model,
                "source_sha256": source_sha256,
            }
        )
    await session.execute(delete(HadithSignal))
    if rows:
        await session.execute(insert(HadithSignal), rows)
    return report
