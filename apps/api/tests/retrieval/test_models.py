from __future__ import annotations

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from src.models import (
    EmbeddingRun,
    HadithEmbedding,
    HadithSearch,
    QuranVerse,
    QuranVerseEmbedding,
    QuranVerseSearch,
)
from src.models.retrieval import INDEXED_EMBEDDINGS, hnsw_index_name


async def _verse_id(session, surah: int, ayah: int) -> int:
    return await session.scalar(
        select(QuranVerse.id).where(QuranVerse.surah == surah, QuranVerse.ayah == ayah)
    )


async def test_a_vector_is_stored_with_its_model_and_size(world):
    verse_id = await _verse_id(world, 30, 50)
    world.add(
        QuranVerseEmbedding(
            verse_id=verse_id,
            model="m",
            dimensions=3,
            document_sha256="0" * 64,
            embedding=[0.1, 0.2, 0.3],
        )
    )
    await world.flush()

    stored = await world.scalar(select(QuranVerseEmbedding.embedding))
    assert [round(value, 3) for value in stored] == [0.1, 0.2, 0.3]


async def test_a_vector_whose_size_is_not_its_dimensions_is_refused(world):
    hadith_id = await world.scalar(select(HadithSearch.hadith_id).limit(1))
    world.add(
        HadithEmbedding(
            hadith_id=hadith_id,
            model="m",
            dimensions=4,
            document_sha256="0" * 64,
            embedding=[0.1, 0.2, 0.3],
        )
    )
    with pytest.raises(IntegrityError, match="dimensions_match"):
        await world.flush()


async def test_a_run_of_an_unknown_corpus_is_refused(db_session):
    db_session.add(EmbeddingRun(corpus="tafsir", provider="openai", model="m", dimensions=8))
    with pytest.raises(IntegrityError, match="corpus"):
        await db_session.flush()


async def test_the_database_computes_the_full_text_vector_of_every_search_copy(world):
    vectors = await world.scalar(
        select(func.count()).where(
            QuranVerseSearch.search_vector.op("@@")(func.to_tsquery("simple", "الارض"))
        )
    )
    hadiths = await world.scalar(select(func.count()).select_from(HadithSearch))
    filled = await world.scalar(select(func.count()).where(HadithSearch.search_vector.is_not(None)))

    assert vectors >= 1
    assert filled == hadiths > 0


async def test_each_default_embedding_has_its_hnsw_index_on_both_tables(world):
    names = set(
        (
            await world.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = 'vectors' AND indexdef LIKE '%hnsw%'"
                )
            )
        ).scalars()
    )

    assert names == {
        hnsw_index_name(table, model, dimensions)
        for table in ("quran_verse_embeddings", "hadith_embeddings")
        for model, dimensions in INDEXED_EMBEDDINGS
    }
