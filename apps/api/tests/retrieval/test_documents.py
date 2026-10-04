from __future__ import annotations

from sqlalchemy import select

from src.models import EmbeddedCorpus, Hadith, QuranAnnotation, QuranVerse, QuranVerseSearch
from src.retrieval import documents
from src.retrieval.documents import (
    RetrievalDocument,
    hadith_body,
    hadith_concepts,
    hadith_documents,
    quran_documents,
    unique_concepts,
)
from src.scripture.text import search_copy
from tests.scripture.fixtures import hadith_text, verse_text


def test_a_document_joins_its_text_and_its_concepts_and_hashes_both():
    bare = RetrievalDocument(EmbeddedCorpus.QURAN, 1, "نص", ())
    rich = RetrievalDocument(EmbeddedCorpus.QURAN, 1, "نص", ("رحمة", "إحياء"))

    assert bare.body == "نص"
    assert rich.body == "نص | رحمة، إحياء"
    assert bare.sha256 != rich.sha256


def test_long_texts_and_long_concept_lists_are_cut_at_a_word(monkeypatch):
    monkeypatch.setattr(documents, "CONCEPTS_MAX_CHARS", 9)
    document = documents.verse_document(1, "كلمة " * 400, ("مفهوم أول", "مفهوم ثان"))

    assert len(document.text) <= documents.TEXT_MAX_CHARS
    assert not document.text.endswith(" ")
    assert document.body.endswith("| مفهوم")
    assert documents._clip("abcdefghij", 4) == "abcd"


def test_concepts_are_kept_once_in_order_and_blanks_dropped():
    assert unique_concepts([["رحمة", " "], ["الرَّحمة", "رحمه", "إحياء"]]) == (
        "رحمة",
        "الرَّحمة",
        "إحياء",
    )


def test_a_hadith_body_leaves_out_a_clear_chain_and_folds_the_rest():
    with_chain = hadith_text("bukhari", 1032)
    whole = "قال: إنما الأمر"

    body = hadith_body(with_chain)

    assert body
    assert body in search_copy(with_chain)
    assert len(body) < len(search_copy(with_chain))
    assert hadith_body(whole) == search_copy(whole)


async def test_every_verse_has_a_document_from_its_search_copy_and_annotations(world):
    folded = dict(
        (
            await world.execute(select(QuranVerseSearch.verse_id, QuranVerseSearch.normalized_text))
        ).all()
    )
    annotated = await world.scalar(
        select(QuranAnnotation).where(QuranAnnotation.surah == 30, QuranAnnotation.ayah == 50)
    )
    verse_id = await world.scalar(
        select(QuranVerse.id).where(QuranVerse.surah == 30, QuranVerse.ayah == 50)
    )

    all_docs = await quran_documents(world)
    one = await quran_documents(world, [verse_id])

    assert len(all_docs) == len(folded)
    assert one[0].text == folded[verse_id]
    assert annotated.key_concepts[0] in one[0].concepts
    # The displayed text never enters a document, only its folded copy.
    assert verse_text(30, 50) not in one[0].body
    assert any(not doc.concepts for doc in all_docs)


async def test_hadith_documents_carry_the_signals_of_every_matched_narration(world):
    ids = dict(
        (
            await world.execute(
                select(Hadith.number, Hadith.id).where(Hadith.collection == "bukhari")
            )
        ).all()
    )

    concepts = await hadith_concepts(world)
    in_muslim = await hadith_concepts(world, collections=["muslim"])
    bukhari = await hadith_documents(world, collections=["bukhari"])
    chosen = await hadith_documents(world, hadith_ids=[ids["1032"]])

    assert concepts[ids["1032"]]
    assert ids["1032"] not in in_muslim
    assert {doc.key for doc in bukhari} == set(ids.values())
    assert chosen[0].concepts == concepts[ids["1032"]]
    assert hadith_text("bukhari", 1032) not in chosen[0].body
