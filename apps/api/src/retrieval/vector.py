"""
Semantic search: the stored texts whose document vectors are nearest a query's.

Vectors of several models sit in one table, keyed by model and dimensions
(`src.models.retrieval`). A search names both, casts the column to that size
and orders by cosine distance; for the (model, dimensions) pairs that have an
HNSW index (`INDEXED_MODELS`), PostgreSQL uses it, and for any other pair it
scans the rows of that model exactly, which the benchmark does on purpose.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import EmbeddedCorpus
from src.retrieval.lexical import Hit

# Candidates the HNSW graph walk keeps; above the default 40 so a top 30 stays exact enough.
EF_SEARCH = 100

_TABLES = {
    EmbeddedCorpus.QURAN: ("vectors.quran_verse_embeddings", "verse_id"),
    EmbeddedCorpus.HADITH: ("vectors.hadith_embeddings", "hadith_id"),
}


def _statement(corpus: EmbeddedCorpus, dimensions: int, *, by_collection: bool) -> Any:
    table, key = _TABLES[corpus]
    # The size is an int checked by the caller; it must be literal for the cast to match the index.
    cast = f"(e.embedding::vector({int(dimensions)}))"
    join = ""
    where = "e.model = :model AND e.dimensions = :dimensions"
    if by_collection:
        join = " JOIN corpus.hadiths h ON h.id = e.hadith_id"
        where += " AND h.collection IN :collections"
    sql = (
        f"SELECT e.{key} AS key, 1 - ({cast} <=> :query) AS similarity "  # noqa: S608 - fixed names
        f"FROM {table} e{join} WHERE {where} ORDER BY {cast} <=> :query LIMIT :limit"
    )
    statement = text(sql).bindparams(bindparam("query", type_=VECTOR(int(dimensions))))
    if by_collection:
        statement = statement.bindparams(bindparam("collections", expanding=True))
    return statement


async def nearest(
    session: AsyncSession,
    corpus: EmbeddedCorpus,
    vector: Sequence[float],
    *,
    model: str,
    dimensions: int,
    limit: int = 30,
    collections: Sequence[str] | None = None,
) -> list[Hit]:
    """Return the `limit` texts nearest to `vector`, nearest first, scored by cosine similarity."""
    if len(vector) != dimensions:
        message = f"the query vector has {len(vector)} dimensions, not {dimensions}"
        raise ValueError(message)
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {EF_SEARCH}"))
    by_collection = corpus is EmbeddedCorpus.HADITH and collections is not None
    parameters: dict[str, Any] = {
        "model": model,
        "dimensions": dimensions,
        "query": list(vector),
        "limit": limit,
    }
    if by_collection:
        parameters["collections"] = list(collections or ())
    rows = await session.execute(
        _statement(corpus, dimensions, by_collection=by_collection), parameters
    )
    return [Hit(int(row.key), float(row.similarity)) for row in rows]


async def has_vectors(
    session: AsyncSession, corpus: EmbeddedCorpus, *, model: str, dimensions: int | None
) -> bool:
    """Whether the store holds at least one vector of `model` (of that size) for `corpus`."""
    table, _ = _TABLES[corpus]
    where = "e.model = :model"
    parameters: dict[str, Any] = {"model": model}
    if dimensions is not None:
        where += " AND e.dimensions = :dimensions"
        parameters["dimensions"] = dimensions
    row = await session.execute(
        text(f"SELECT 1 FROM {table} e WHERE {where} LIMIT 1"),  # noqa: S608 - fixed names
        parameters,
    )
    return row.first() is not None
