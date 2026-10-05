"""Query stems, full-text and trigram search, the concept index, vector search and fusion."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.models import EmbeddedCorpus, Hadith, HadithEmbedding, QuranVerse, QuranVerseEmbedding
from src.retrieval.concepts import ConceptIndex, load_concept_index
from src.retrieval.fusion import FusedHit, fuse
from src.retrieval.lexical import Hit, LexicalMethod, idf, search_lexical
from src.retrieval.query import CLITIC_PREFIXES, prefix_query, query_terms, stem
from src.retrieval.vector import nearest
from tests.retrieval.support import fake_vector


def test_a_stem_loses_its_conjunction_and_article_when_three_letters_remain():
    assert stem("والارض") == "ارض"
    assert stem("بالماء") == "ماء"
    assert stem("للناس") == "ناس"
    assert stem("فالله") == "الله"
    assert stem("وما") == "وما"
    assert stem("ولد") == "ولد"
    assert stem("وهولاء") == "وهولاء"
    assert stem("الي") == "الي"


def test_query_terms_are_folded_stems_without_particles_or_repeats():
    assert query_terms("إحياء الأرض بالمطر") == ["احياء", "ارض", "مطر"]
    assert query_terms("في الأرض وفي الأرض") == ["ارض"]
    assert query_terms("ما لا من hello") == ["hello"]
    assert len(query_terms(" ".join(f"كلمة{index}" for index in range(20)))) == 8


def test_a_prefix_query_finds_the_stem_behind_every_clitic():
    query = prefix_query("ارض")

    assert query.count("|") == len(CLITIC_PREFIXES) - 1
    assert "ارض:*" in query
    assert "والارض:*" in query


def test_idf_weighs_rare_terms_above_common_ones():
    assert idf(1000, 1) > idf(1000, 500) > 0


@pytest.mark.parametrize("method", list(LexicalMethod))
async def test_lexical_search_finds_the_verse_that_holds_the_words(world, method):
    verse_id = await world.scalar(
        select(QuranVerse.id).where(QuranVerse.surah == 30, QuranVerse.ayah == 50)
    )

    hits = await search_lexical(world, EmbeddedCorpus.QURAN, ["ارض", "موت"], method=method)

    assert hits[0].key == verse_id
    assert all(hit.score > 0 for hit in hits)
    assert await search_lexical(world, EmbeddedCorpus.QURAN, [], method=method) == []


async def test_hadith_search_can_be_limited_to_some_books(world):
    bukhari = await world.scalar(
        select(Hadith.id).where(Hadith.collection == "bukhari", Hadith.number == "1032")
    )

    everywhere = await search_lexical(world, EmbeddedCorpus.HADITH, ["مطر"])
    in_muslim = await search_lexical(world, EmbeddedCorpus.HADITH, ["مطر"], collections=["muslim"])

    assert bukhari in [hit.key for hit in everywhere]
    assert bukhari not in [hit.key for hit in in_muslim]


def test_the_concept_index_ranks_rare_stems_and_word_pairs_first():
    index = ConceptIndex(
        EmbeddedCorpus.QURAN,
        {
            1: ["إحياء الأرض", "رحمة"],
            2: ["الأرض الواسعة"],
            3: ["رحمة"],
            4: ["الإحياء", "الأرض"],
        },
    )

    hits = index.search("إحياء الأرض")

    assert len(index) == 4
    assert [hit.key for hit in hits][:2] == [1, 4]
    assert hits[0].score > hits[1].score
    assert index.search("رحم", limit=1)[0].key in {1, 3}
    assert index.search("نجوم") == []
    assert index.search("") == []


async def test_concept_indexes_are_built_from_annotations_and_signals(world):
    quran = await load_concept_index(world, EmbeddedCorpus.QURAN)
    hadith = await load_concept_index(world, EmbeddedCorpus.HADITH)
    muslim = await load_concept_index(world, EmbeddedCorpus.HADITH, collections=["muslim"])
    rain = await world.scalar(
        select(Hadith.id).where(Hadith.collection == "bukhari", Hadith.number == "1032")
    )

    assert len(quran) > 0
    assert rain in [hit.key for hit in hadith.search("الدعاء عند المطر")]
    assert rain not in [hit.key for hit in muslim.search("الدعاء عند المطر")]


async def _store_vectors(world, table, key_name, keys, model="m"):
    for key in keys:
        world.add(
            table(
                **{key_name: key},
                model=model,
                dimensions=8,
                document_sha256="0" * 64,
                embedding=fake_vector(str(key)),
            )
        )
    await world.flush()


async def test_vector_search_returns_the_nearest_texts_of_one_model(world):
    verses = list(await world.scalars(select(QuranVerse.id).order_by(QuranVerse.id)))
    await _store_vectors(world, QuranVerseEmbedding, "verse_id", verses)
    await _store_vectors(world, QuranVerseEmbedding, "verse_id", verses[:2], model="other")

    hits = await nearest(
        world, EmbeddedCorpus.QURAN, fake_vector(str(verses[3])), model="m", dimensions=8, limit=3
    )

    assert hits[0].key == verses[3]
    assert hits[0].score == pytest.approx(1.0)
    assert len(hits) == 3
    with pytest.raises(ValueError, match="has 4 dimensions"):
        await nearest(world, EmbeddedCorpus.QURAN, [0.0] * 4, model="m", dimensions=8)


async def test_vector_search_over_hadith_can_be_limited_to_some_books(world):
    rows = (await world.execute(select(Hadith.id, Hadith.collection))).all()
    await _store_vectors(world, HadithEmbedding, "hadith_id", [row.id for row in rows])
    muslim = {row.id for row in rows if row.collection == "muslim"}

    hits = await nearest(
        world,
        EmbeddedCorpus.HADITH,
        fake_vector(str(rows[0].id)),
        model="m",
        dimensions=8,
        collections=["muslim"],
    )
    everywhere = await nearest(
        world, EmbeddedCorpus.HADITH, fake_vector(str(rows[0].id)), model="m", dimensions=8
    )

    assert {hit.key for hit in hits} == muslim
    assert len(everywhere) == len(rows)


def test_rrf_rewards_texts_found_by_several_lists_and_counts_a_repeat_once():
    fused = fuse(
        {
            "vector:q1": [Hit(1, 0.9), Hit(2, 0.8), Hit(1, 0.7)],
            "fts:q1": [Hit(2, 3.0), Hit(3, 2.0)],
        },
        weights={"fts": 0.5},
    )

    assert [hit.key for hit in fused] == [2, 1, 3]
    assert fused[0] == FusedHit(2, 1 / 62 + 0.5 / 61, (("vector:q1", 2), ("fts:q1", 1)))
    assert fused[1].best_rank() == 1
    assert fuse({}) == []


async def test_a_pool_of_ids_narrows_the_lexical_and_the_vector_search(world):
    rows = (
        await world.execute(select(Hadith.id, Hadith.number).where(Hadith.collection == "bukhari"))
    ).all()
    ids = {row.number: row.id for row in rows}

    everywhere = await search_lexical(world, EmbeddedCorpus.HADITH, ["مطر"])
    pooled = await search_lexical(world, EmbeddedCorpus.HADITH, ["مطر"], ids=[ids["1032"]])
    elsewhere = await search_lexical(world, EmbeddedCorpus.HADITH, ["مطر"], ids=[ids["1"]])
    await _store_vectors(world, HadithEmbedding, "hadith_id", [row.id for row in rows])
    near = await nearest(
        world,
        EmbeddedCorpus.HADITH,
        fake_vector(str(ids["1032"])),
        model="m",
        dimensions=8,
        ids=[ids["8"], ids["1"]],
    )

    assert ids["1032"] in [hit.key for hit in everywhere]
    assert [hit.key for hit in pooled] == [ids["1032"]]
    assert elsewhere == []
    assert {hit.key for hit in near} == {ids["8"], ids["1"]}
