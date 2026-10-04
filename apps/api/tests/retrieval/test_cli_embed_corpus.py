from __future__ import annotations

import logging

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from src.cli import embed_corpus
from src.config import AiProvider
from src.models import HadithEmbedding, QuranVerseEmbedding
from tests.retrieval.support import EmbeddingClient


def _settings(make_settings, **values):
    return make_settings(ai_openai={"embedding_model": "m", "api_key": "k"}, **values)


async def _count(maker, table) -> int:
    async with maker() as session:
        return await session.scalar(select(func.count()).select_from(table))


async def test_nothing_is_embedded_without_a_model_or_a_key(make_settings, capsys):
    code = await embed_corpus.run([], settings=make_settings())

    assert code == 0
    assert "embeddings skipped: openai" in capsys.readouterr().out


async def test_an_unknown_corpus_is_refused(make_settings):
    with pytest.raises(SystemExit):
        await embed_corpus.run(["tafsir"], settings=make_settings())


async def test_a_dry_run_counts_what_would_be_sent_and_calls_nothing(
    make_settings, world_maker, capsys
):
    client = EmbeddingClient()

    code = await embed_corpus.run(
        ["--dry-run", "--collections", "bukhari", "--concurrency", "1"],
        settings=_settings(make_settings),
        sessionmaker=world_maker,
        client=client,
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "quran: " in out
    assert "hadith: 4 documents, 4 to embed" in out
    assert "dry run, nothing sent" in out
    assert client.embedded == []


async def test_both_corpora_are_embedded_with_the_provider_defaults(
    make_settings, world_maker, capsys
):
    client = EmbeddingClient(AiProvider.OVH)
    settings = make_settings(ai_ovh={"embedding_model": "ovh-embed", "embedding_dimensions": 8})

    code = await embed_corpus.run(
        ["--provider", "ovh", "--concurrency", "1"],
        settings=settings,
        sessionmaker=world_maker,
        client=client,
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "quran: ovh-embed (8 dims)" in out
    assert "hadith: ovh-embed (8 dims)" in out
    assert await _count(world_maker, QuranVerseEmbedding) > 0
    assert await _count(world_maker, HadithEmbedding) > 0
    assert max(len(batch) for batch in client.embedded) <= 25


async def test_a_failed_run_exits_one(make_settings, world_maker, capsys):
    client = EmbeddingClient(fail_on_call=1)

    code = await embed_corpus.run(
        ["quran", "--model", "m2", "--dimensions", "8", "--concurrency", "1"],
        settings=_settings(make_settings),
        sessionmaker=world_maker,
        client=client,
    )

    assert code == 1
    assert "embedding failed: AiCallError" in capsys.readouterr().err


async def test_the_command_builds_its_own_client_and_engine_when_given_none(
    make_settings, monkeypatch
):
    seen = {}

    def fake_client_for(settings, http, *, provider):
        seen["provider"] = provider
        return EmbeddingClient(provider)

    async def fail(_session, **_kwargs):
        raise OperationalError("SELECT 1", {}, Exception("timeout"))

    disposed = []

    async def dispose() -> None:
        disposed.append(True)

    monkeypatch.setattr(embed_corpus, "client_for", fake_client_for)
    monkeypatch.setattr(embed_corpus, "hadith_documents", fail)
    monkeypatch.setattr(embed_corpus, "dispose_engine", dispose)

    code = await embed_corpus.run(["hadith"], settings=_settings(make_settings))

    assert code == 1
    assert seen["provider"] is AiProvider.OPENAI
    assert disposed == [True]


def test_main_runs_the_command_and_quiets_the_http_log(monkeypatch):
    async def fake_run(argv):
        return 7

    monkeypatch.setattr(embed_corpus, "run", fake_run)

    assert embed_corpus.main(["quran"]) == 7
    assert logging.getLogger("httpx").level == logging.WARNING
