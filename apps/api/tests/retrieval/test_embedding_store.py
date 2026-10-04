from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.ai.errors import AiCallError
from src.config import AiProvider
from src.models import (
    EmbeddedCorpus,
    EmbeddingRun,
    HadithEmbedding,
    QuranVerseEmbedding,
)
from src.retrieval.documents import RetrievalDocument, hadith_documents, quran_documents
from src.retrieval.embedding_store import (
    ABANDONED,
    STALE_AFTER,
    CorpusEmbedder,
    SpendCapReachedError,
    batch_limit,
    batches,
    stored_hashes,
)
from tests.retrieval.support import EmbeddingClient


async def _documents(maker, corpus):
    async with maker() as session:
        if corpus is EmbeddedCorpus.QURAN:
            return await quran_documents(session)
        return await hadith_documents(session)


async def _runs(maker):
    async with maker() as session:
        return list(await session.scalars(select(EmbeddingRun).order_by(EmbeddingRun.id)))


def test_documents_go_in_batches_no_larger_than_the_provider_takes():
    assert [list(batch) for batch in batches([1, 2, 3, 4, 5], 2)] == [[1, 2], [3, 4], [5]]
    assert batch_limit(AiProvider.OVH) == 25
    assert batch_limit(AiProvider.OPENAI) == 2048


async def test_a_run_embeds_every_document_records_its_cost_and_a_second_run_sends_nothing(
    world_maker,
):
    client = EmbeddingClient(cost_per_call=0.01)
    embedder = CorpusEmbedder(
        world_maker, client, model="m", dimensions=8, batch_size=4, concurrency=1
    )
    documents = await _documents(world_maker, EmbeddedCorpus.QURAN)

    first = await embedder.run(EmbeddedCorpus.QURAN, documents)
    second = await embedder.run(EmbeddedCorpus.QURAN, documents)

    expected_batches = -(-len(documents) // 4)
    assert (first.embedded, first.unchanged, first.batches) == (len(documents), 0, expected_batches)
    assert first.cost_usd == pytest.approx(0.01 * expected_batches)
    assert first.input_tokens == 10 * len(documents)
    assert len(first.batch_seconds) == expected_batches
    assert (second.embedded, second.unchanged, second.batches) == (0, len(documents), 0)
    runs = await _runs(world_maker)
    assert [(run.status, run.embedded, run.dimensions) for run in runs] == [
        ("done", len(documents), 8),
        ("done", 0, 8),
    ]
    assert runs[0].cost_usd == pytest.approx(first.cost_usd)
    assert runs[0].finished_at is not None
    async with world_maker() as session:
        hashes = await stored_hashes(session, EmbeddedCorpus.QURAN, "m", 8)
        assert hashes == {doc.key: doc.sha256 for doc in documents}
        assert await stored_hashes(session, EmbeddedCorpus.QURAN, "m", None) == hashes
        assert await stored_hashes(session, EmbeddedCorpus.QURAN, "other", 8) == {}


async def test_a_changed_document_is_embedded_again_and_alone(world_maker):
    client = EmbeddingClient()
    embedder = CorpusEmbedder(world_maker, client, model="m", dimensions=None, concurrency=1)
    documents = await _documents(world_maker, EmbeddedCorpus.HADITH)
    await embedder.run(EmbeddedCorpus.HADITH, documents)
    changed = RetrievalDocument(
        documents[0].corpus, documents[0].key, documents[0].text, ("مفهوم جديد",)
    )

    report = await embedder.run(EmbeddedCorpus.HADITH, [changed, *documents[1:]])

    assert (report.embedded, report.dimensions) == (1, 8)
    assert client.embedded[-1] == [changed.body]
    async with world_maker() as session:
        stored = await session.scalar(
            select(HadithEmbedding.document_sha256).where(HadithEmbedding.hadith_id == changed.key)
        )
    assert stored == changed.sha256


async def test_a_provider_failure_is_recorded_and_what_was_finished_is_kept(world_maker):
    client = EmbeddingClient(fail_on_call=2)
    embedder = CorpusEmbedder(
        world_maker, client, model="m", dimensions=8, batch_size=2, concurrency=1
    )
    documents = await _documents(world_maker, EmbeddedCorpus.QURAN)

    with pytest.raises(AiCallError):
        await embedder.run(EmbeddedCorpus.QURAN, documents)

    (run,) = await _runs(world_maker)
    assert run.status == "failed"
    assert run.embedded == 2
    assert "AiCallError" in run.error
    async with world_maker() as session:
        kept = list(await session.scalars(select(QuranVerseEmbedding.verse_id)))
    assert len(kept) == 2


async def test_the_spend_cap_stops_a_run_before_the_next_batch(world_maker):
    client = EmbeddingClient(cost_per_call=0.5)
    embedder = CorpusEmbedder(
        world_maker, client, model="m", dimensions=8, batch_size=2, concurrency=1, max_cost_usd=0.5
    )
    documents = await _documents(world_maker, EmbeddedCorpus.QURAN)

    with pytest.raises(SpendCapReachedError, match=r"\$0.50"):
        await embedder.run(EmbeddedCorpus.QURAN, documents)

    (run,) = await _runs(world_maker)
    assert (run.status, run.embedded) == ("failed", 2)
    assert len(client.embedded) == 1


async def test_a_run_whose_process_was_killed_is_closed_by_the_next_run(world_maker):
    now = datetime.now(UTC)
    async with world_maker() as session, session.begin():
        for started in (now - STALE_AFTER - timedelta(minutes=1), now - timedelta(minutes=5)):
            session.add(
                EmbeddingRun(
                    corpus="quran", provider="openai", model="m", dimensions=8, started_at=started
                )
            )
    embedder = CorpusEmbedder(world_maker, EmbeddingClient(), model="m", dimensions=8)

    await embedder.run(EmbeddedCorpus.QURAN, [])

    killed, recent, finished = await _runs(world_maker)
    assert (killed.status, killed.error) == ("failed", ABANDONED)
    assert killed.finished_at is not None
    # A run that may still be working elsewhere is left alone.
    assert (recent.status, recent.error) == ("running", None)
    assert finished.status == "done"
