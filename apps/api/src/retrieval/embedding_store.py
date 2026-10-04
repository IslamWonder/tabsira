"""
Fill the vector tables: embed the documents that have no vector yet, or a stale one.

A run compares each document's SHA-256 with the one stored next to its vector
for the same model and size, and embeds only the documents that are new or
changed (a corrected verse, a new annotation), in batches. Each batch is
written with its share of the run's counters in one transaction, so a run that
stops (a network fault, the spend cap) keeps what it finished and the next run
starts where it stopped. Every run is recorded in `embedding_runs` with the
tokens it used and what they cost at the provider prices of the settings.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.ai.client import ModelClient
from src.config import AiProvider
from src.models import (
    EmbeddedCorpus,
    EmbeddingRun,
    EmbeddingRunStatus,
    HadithEmbedding,
    QuranVerseEmbedding,
)
from src.retrieval.documents import RetrievalDocument

DEFAULT_BATCH_SIZE = 128
DEFAULT_CONCURRENCY = 4
# Texts one embedding request may carry: OVH answers HTTP 400 above 25 (measured);
# OpenAI documents 2,048.
BATCH_LIMITS = {AiProvider.OVH: 25, AiProvider.OPENAI: 2048}

_TABLES: dict[EmbeddedCorpus, type[QuranVerseEmbedding] | type[HadithEmbedding]] = {
    EmbeddedCorpus.QURAN: QuranVerseEmbedding,
    EmbeddedCorpus.HADITH: HadithEmbedding,
}


def _key_name(table: type[QuranVerseEmbedding] | type[HadithEmbedding]) -> str:
    return "verse_id" if table is QuranVerseEmbedding else "hadith_id"


class SpendCapReachedError(RuntimeError):
    """The run stopped because its cost reached the cap; what it finished is kept."""

    def __init__(self, cap: float) -> None:
        super().__init__(f"spend cap of ${cap:.2f} reached")


@dataclass
class RunReport:
    """What one run over one corpus did."""

    corpus: EmbeddedCorpus
    model: str
    dimensions: int | None
    documents: int
    unchanged: int
    embedded: int = 0
    batches: int = 0
    input_tokens: int = 0
    cost_usd: float = 0.0
    run_id: int | None = None
    stopped: str | None = None
    batch_seconds: list[float] = field(default_factory=list)


async def stored_hashes(
    session: AsyncSession, corpus: EmbeddedCorpus, model: str, dimensions: int | None
) -> dict[int, str]:
    """Return the document hash stored with each vector of `model` (of that size, if given)."""
    table = _TABLES[corpus]
    key = getattr(table, _key_name(table))
    query = select(key, table.document_sha256).where(table.model == model)
    if dimensions is not None:
        query = query.where(table.dimensions == dimensions)
    return {int(row[0]): str(row[1]) for row in await session.execute(query)}


def batches[T](items: Sequence[T], size: int) -> list[Sequence[T]]:
    return [items[start : start + size] for start in range(0, len(items), size)]


def batch_limit(provider: AiProvider) -> int:
    return BATCH_LIMITS[provider]


class CorpusEmbedder:
    """Embeds the documents of one corpus with one model and size, through one client."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        client: ModelClient,
        *,
        model: str,
        dimensions: int | None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        concurrency: int = DEFAULT_CONCURRENCY,
        max_cost_usd: float | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._client = client
        self.model = model
        self.dimensions = dimensions
        self._batch_size = min(batch_size, batch_limit(client.provider))
        self._concurrency = concurrency
        self._max_cost = max_cost_usd
        self._clock = clock or time.perf_counter
        self._spent = 0.0

    async def run(
        self, corpus: EmbeddedCorpus, documents: Sequence[RetrievalDocument]
    ) -> RunReport:
        """Embed what is new or changed; record the run; raise after recording a failure."""
        async with self._sessionmaker() as session:
            known = await stored_hashes(session, corpus, self.model, self.dimensions)
        todo = [doc for doc in documents if known.get(doc.key) != doc.sha256]
        report = RunReport(
            corpus, self.model, self.dimensions, len(documents), len(documents) - len(todo)
        )
        report.run_id = await self._start(report)
        gate = asyncio.Semaphore(self._concurrency)
        failures: list[Exception] = []

        async def one(batch: Sequence[RetrievalDocument]) -> None:
            # After a failure the waiting batches are skipped; those in flight finish
            # and are kept, never cut in the middle of their transaction.
            async with gate:
                if failures:
                    return
                if self._max_cost is not None and self._spent >= self._max_cost:
                    failures.append(SpendCapReachedError(self._max_cost))
                    return
                try:
                    await self._embed_batch(corpus, batch, report)
                except Exception as error:  # recorded below, then raised to the caller
                    failures.append(error)

        await asyncio.gather(*(one(batch) for batch in batches(todo, self._batch_size)))
        if failures:
            error = failures[0]
            report.stopped = f"{type(error).__name__}: {error}"
            await self._finish(report, EmbeddingRunStatus.FAILED, report.stopped)
            raise error
        await self._finish(report, EmbeddingRunStatus.DONE, None)
        return report

    async def _start(self, report: RunReport) -> int:
        async with self._sessionmaker() as session, session.begin():
            run = EmbeddingRun(
                corpus=report.corpus.value,
                provider=self._client.provider.value,
                model=self.model,
                dimensions=self.dimensions or 0,
                documents=report.documents,
                unchanged=report.unchanged,
                cost_usd=0.0,
            )
            session.add(run)
            await session.flush()
            return run.id

    async def _embed_batch(
        self, corpus: EmbeddedCorpus, batch: Sequence[RetrievalDocument], report: RunReport
    ) -> None:
        started = self._clock()
        result = await self._client.embed(
            [doc.body for doc in batch], model=self.model, dimensions=self.dimensions
        )
        cost = result.record.cost_usd or 0.0
        tokens = result.record.usage.input_tokens
        self._spent += cost
        size = len(result.vectors[0])
        table = _TABLES[corpus]
        key_name = _key_name(table)
        rows = [
            {
                key_name: doc.key,
                "model": self.model,
                "dimensions": size,
                "document_sha256": doc.sha256,
                "embedding": vector,
            }
            for doc, vector in zip(batch, result.vectors, strict=True)
        ]
        statement = insert(table).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=[key_name, "model", "dimensions"],
            set_={
                "document_sha256": statement.excluded.document_sha256,
                "embedding": statement.excluded.embedding,
                "embedded_at": datetime.now(UTC),
            },
        )
        async with self._sessionmaker() as session, session.begin():
            await session.execute(statement)
            await session.execute(
                update(EmbeddingRun)
                .where(EmbeddingRun.id == report.run_id)
                .values(
                    embedded=EmbeddingRun.embedded + len(batch),
                    batches=EmbeddingRun.batches + 1,
                    input_tokens=EmbeddingRun.input_tokens + tokens,
                    cost_usd=EmbeddingRun.cost_usd + cost,
                    dimensions=size,
                )
            )
        report.embedded += len(batch)
        report.batches += 1
        report.input_tokens += tokens
        report.cost_usd += cost
        report.dimensions = size
        report.batch_seconds.append(self._clock() - started)

    async def _finish(
        self, report: RunReport, status: EmbeddingRunStatus, error: str | None
    ) -> None:
        async with self._sessionmaker() as session, session.begin():
            await session.execute(
                update(EmbeddingRun)
                .where(EmbeddingRun.id == report.run_id)
                .values(status=status.value, error=error, finished_at=datetime.now(UTC))
            )
