"""
Lexical search over the folded search copies (`quran_verse_search`, `hadith_search`).

Two methods, compared by the retrieval benchmark (docs/BENCHMARK.md):

- `FTS`: PostgreSQL full-text search with the `simple` configuration on the
  stored `search_vector` of each copy (its words as they are, no stemmer, the
  folding already done). Each query stem is looked up as a prefix behind every
  clitic (`src.retrieval.query.prefix_query`), on the GIN index.
- `TRIGRAM`: pg_trgm word similarity between each stem and the copy, on the
  trigram index, above `TRIGRAM_THRESHOLD`.

Both score a text by the stems it holds, each weighted by its inverse document
frequency in the corpus searched (a stem found in every hadith says nothing),
so a text that holds the rare words of the query comes first. The search
copies are never displayed; a hit is an id and a score.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, Float, and_, any_, bindparam, case, func, literal, or_, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.models import EmbeddedCorpus, Hadith, HadithSearch, QuranVerseSearch
from src.retrieval.query import prefix_query

TRIGRAM_THRESHOLD = 0.6


class LexicalMethod(StrEnum):
    FTS = "fts"
    TRIGRAM = "trigram"


@dataclass(frozen=True, slots=True)
class Hit:
    """A stored text a search found: its verse or hadith id, and its score (higher is better)."""

    key: int
    score: float


def _scope(
    corpus: EmbeddedCorpus, collections: Sequence[str] | None
) -> tuple[Any, Any, Any, list[Any]]:
    """Return the key, the folded text, the search vector and the filters of a corpus."""
    if corpus is EmbeddedCorpus.QURAN:
        return (
            QuranVerseSearch.verse_id,
            QuranVerseSearch.normalized_text,
            QuranVerseSearch.search_vector,
            [],
        )
    filters = [] if collections is None else [Hadith.collection.in_(collections)]
    return HadithSearch.hadith_id, HadithSearch.normalized_text, HadithSearch.search_vector, filters


def _from(corpus: EmbeddedCorpus, query: Any) -> Any:
    if corpus is EmbeddedCorpus.HADITH:
        return query.join(Hadith, Hadith.id == HadithSearch.hadith_id)
    return query


def idf(documents: int, frequency: int) -> float:
    """Return the BM25 inverse document frequency of a term found in `frequency` of `documents`."""
    return math.log(1.0 + (documents - frequency + 0.5) / (frequency + 0.5))


async def search_lexical(
    session: AsyncSession,
    corpus: EmbeddedCorpus,
    terms: Sequence[str],
    *,
    method: LexicalMethod = LexicalMethod.FTS,
    limit: int = 30,
    collections: Sequence[str] | None = None,
    ids: Collection[int] | None = None,
) -> list[Hit]:
    """
    Return the texts that hold the most informative stems of `terms`, best first.

    `ids` narrows the search to a pool of texts (the narrations of the enriched Sunnah
    file); the document frequencies are counted inside the pool, so a stem common in the
    pool weighs little there whatever its rarity in the whole store.
    """
    if not terms:
        return []
    key, folded, vector, filters = _scope(corpus, collections)
    if ids is not None:
        filters = [*filters, key == any_(bindparam("ids", list(ids), type_=ARRAY(BigInteger)))]
    if method is LexicalMethod.FTS:
        matches = [vector.op("@@")(func.to_tsquery("simple", prefix_query(term))) for term in terms]
    else:
        await session.execute(
            select(
                func.set_config("pg_trgm.word_similarity_threshold", str(TRIGRAM_THRESHOLD), True)
            )
        )
        matches = [literal(term).op("<%")(folded) for term in terms]
    found_any = or_(*matches)
    # One count per term, each on its own index scan: a FILTER over every row was ten
    # times slower on the 65,712 hadiths.
    counted = select(
        _from(corpus, select(func.count(key))).where(*filters).scalar_subquery(),
        *[
            _from(corpus, select(func.count(key))).where(match, *filters).scalar_subquery()
            for match in matches
        ],
    )
    counts = (await session.execute(counted)).one()
    documents = int(counts[0])
    weights = [idf(documents, int(counts[index + 1])) for index in range(len(terms))]
    if method is LexicalMethod.FTS:
        parts: list[ColumnElement[float]] = [
            case((match, literal(weight, Float)), else_=literal(0.0, Float))
            for match, weight in zip(matches, weights, strict=True)
        ]
    else:
        parts = [
            func.word_similarity(term, folded) * literal(weight, Float)
            for term, weight in zip(terms, weights, strict=True)
        ]
    score = sum(parts[1:], parts[0]).label("score")
    rows = await session.execute(
        _from(corpus, select(key.label("key"), score))
        .where(and_(found_any, *filters))
        .order_by(score.desc(), key)
        .limit(limit)
    )
    return [Hit(int(row.key), float(row.score)) for row in rows if row.score > 0]
