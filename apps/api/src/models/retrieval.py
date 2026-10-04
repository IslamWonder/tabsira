"""
The vectors of the scripture store, for semantic search, and the runs that built them.

One row per text and per embedding model: `model` and `dimensions` are part of
the key, so the vectors of several models live side by side (the benchmark
compares them, and switching provider switches the model). A vector is built
from a retrieval document (`src.retrieval.documents`): the folded search copy
of the text and the model-written concepts that describe it. Its SHA-256 is
kept, so a text or an annotation that changed is embedded again and nothing
else is. Nothing here is ever displayed.

pgvector indexes a column of one size only, so each provider's default
(model, dimensions), as measured by the retrieval benchmark (docs/BENCHMARK.md),
has its own HNSW index: a partial index on the vector cast to its size
(`INDEXED_EMBEDDINGS`). Vectors of any other model can be stored and searched
too, by an exact scan, as the benchmark does.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base

SHA256_LENGTH = 64
# pgvector's HNSW index takes vectors of at most 2,000 dimensions.
MAX_INDEXED_DIMENSIONS = 2000
DIMENSIONS_MATCH = "vector_dims(embedding) = dimensions"
DIMENSIONS_RANGE = f"dimensions BETWEEN 1 AND {MAX_INDEXED_DIMENSIONS}"


# The default embedding of each provider (docs/BENCHMARK.md), each with its HNSW index.
INDEXED_EMBEDDINGS = (("text-embedding-3-large", 1536), ("bge-m3", 1024))


def hnsw_index_name(table: str, model: str, dimensions: int) -> str:
    return f"ix_{table}_hnsw_{model.replace('-', '_').replace('.', '_')}_{dimensions}"


def hnsw_indexes(table: str) -> tuple[Index, ...]:
    """Return the partial HNSW index of every indexed (model, dimensions) of `table`."""
    return tuple(
        Index(
            hnsw_index_name(table, model, dimensions),
            text(f"(embedding::vector({dimensions})) vector_cosine_ops"),
            postgresql_using="hnsw",
            postgresql_where=text(f"model = '{model}' AND dimensions = {dimensions}"),
        )
        for model, dimensions in INDEXED_EMBEDDINGS
    )


class EmbeddedCorpus(StrEnum):
    """Which half of the scripture store a vector or a run belongs to."""

    QURAN = "quran"
    HADITH = "hadith"


class EmbeddingRunStatus(StrEnum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


def _one_of(column: str, enum: type[StrEnum]) -> str:
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class QuranVerseEmbedding(Base):
    """The vector of one verse's retrieval document under one embedding model."""

    __tablename__ = "quran_verse_embeddings"
    __table_args__ = (
        CheckConstraint(DIMENSIONS_MATCH, name="dimensions_match"),
        CheckConstraint(DIMENSIONS_RANGE, name="dimensions_range"),
        Index("ix_quran_verse_embeddings_model_dimensions", "model", "dimensions"),
        *hnsw_indexes("quran_verse_embeddings"),
    )

    verse_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("quran_verses.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(String(64), primary_key=True)
    dimensions: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    document_sha256: Mapped[str] = mapped_column(String(SHA256_LENGTH))
    embedding: Mapped[Any] = mapped_column(VECTOR())
    embedded_at: Mapped[datetime] = _now()


class HadithEmbedding(Base):
    """The vector of one hadith's retrieval document under one embedding model."""

    __tablename__ = "hadith_embeddings"
    __table_args__ = (
        CheckConstraint(DIMENSIONS_MATCH, name="dimensions_match"),
        CheckConstraint(DIMENSIONS_RANGE, name="dimensions_range"),
        Index("ix_hadith_embeddings_model_dimensions", "model", "dimensions"),
        *hnsw_indexes("hadith_embeddings"),
    )

    hadith_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hadiths.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(String(64), primary_key=True)
    dimensions: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    document_sha256: Mapped[str] = mapped_column(String(SHA256_LENGTH))
    embedding: Mapped[Any] = mapped_column(VECTOR())
    embedded_at: Mapped[datetime] = _now()


class EmbeddingRun(Base):
    """One run of `src.cli.embed_corpus` over one corpus: what it embedded and what it cost."""

    __tablename__ = "embedding_runs"
    __table_args__ = (
        CheckConstraint(_one_of("corpus", EmbeddedCorpus), name="corpus"),
        CheckConstraint(_one_of("status", EmbeddingRunStatus), name="status"),
        Index("ix_embedding_runs_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    corpus: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(64))
    dimensions: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String(16), server_default=text("'running'"))
    # Documents in scope, already up to date, and embedded by this run.
    documents: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    unchanged: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    embedded: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    batches: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    input_tokens: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    # US dollars at the provider prices of the settings; None for a model without a price.
    cost_usd: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = _now()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
