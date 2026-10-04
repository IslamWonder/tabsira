"""The annotated corpus: its annotations joined to the stored verses, never carrying a verse."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import func, select

from src.cli import import_scripture
from src.models import QuranAnnotation, QuranVerse
from src.scripture.annotations import (
    ANNOTATION_KEYS,
    AnnotationImportError,
    annotation_row,
    check_records,
    import_annotations,
)
from src.scripture.files import file_sha256
from src.scripture.text import search_copy
from tests.scripture.fixtures import fixture_path, load_json, store_quran, verse_text

SHA = "a" * 64


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)


def _echoes(text: str, verse: str) -> bool:
    return f" {search_copy(verse)} " in f" {search_copy(text)} "


def _records() -> dict[tuple[int, int], dict]:
    return {(r["surah_no"], r["ayah_no_surah"]): r for r in load_json("quran-annotations.json")}


async def _stored(session) -> dict[tuple[int, int], QuranAnnotation]:
    return {
        (row.surah, row.ayah): row for row in (await session.scalars(select(QuranAnnotation))).all()
    }


async def test_annotations_are_stored_by_verse_and_never_carry_the_verse(quran_session):
    report = await import_annotations(quran_session, load_json("quran-annotations.json"), SHA)

    stored = await _stored(quran_session)
    records = _records()
    echoing = 0
    assert report.verses == len(records) == len(stored)
    for key, row in stored.items():
        verses = (records[key]["text_ar"], verse_text(*key))
        original = {k: records[key]["arabic_annotation"][k] for k in ANNOTATION_KEYS}
        echoing += sum(
            1 for text in _strings(original) if any(_echoes(text, verse) for verse in verses)
        )
        kept = [*_strings(row.annotation), *row.keywords_ar, *row.key_concepts, *row.semantic_tags]
        assert not any(_echoes(text, verse) for text in kept for verse in verses)
        assert set(row.annotation) == set(ANNOTATION_KEYS)
        assert (row.source_ayah_id, row.source_sha256) == (records[key]["ayah_id"], SHA)
    assert report.echoes_left_out == echoing > 0
    plain = stored[(1, 1)]
    assert plain.annotation == {k: records[(1, 1)]["arabic_annotation"][k] for k in ANNOTATION_KEYS}
    assert not {"text", "text_ar"} & set(QuranAnnotation.__table__.columns.keys())


async def test_keys_outside_the_seven_are_left_behind(quran_session):
    await import_annotations(quran_session, load_json("quran-annotations.json"), SHA)
    extra = set(_records()[(2, 2)]["arabic_annotation"]) - set(ANNOTATION_KEYS)

    row = await quran_session.get(QuranAnnotation, (2, 2))

    assert extra
    assert row is not None
    assert not extra & set(row.annotation)


async def test_the_queried_fields_absorb_the_schema_drift(quran_session):
    await import_annotations(quran_session, load_json("quran-annotations.json"), SHA)

    misspelt = await quran_session.get(QuranAnnotation, (2, 49))
    lone_string = await quran_session.get(QuranAnnotation, (30, 2))
    plain = await quran_session.get(QuranAnnotation, (1, 1))

    assert misspelt is not None
    assert misspelt.annotation["islamic_cognitive_dimension"]["islamic_domain"] == "qsas"
    assert misspelt.islamic_domain == "qasas"
    assert lone_string is not None
    assert isinstance(lone_string.annotation["islamic_cognitive_dimension"]["sub_topics"], str)
    assert plain is not None
    raw = plain.annotation
    assert plain.categories == raw["categories"]
    assert plain.key_concepts == raw["search_retrieval_fields"]["key_concepts"]
    assert plain.keywords_ar == raw["search_retrieval_fields"]["keywords_ar"]
    assert plain.semantic_tags == raw["semantic_tags_entities"]["semantic_tags"]
    assert plain.annotation_model == "gpt-4o-mini"


def test_a_string_holding_the_verse_is_left_out_wherever_it_sits():
    verse = verse_text(112, 1)
    record = {
        "ayah_id": 1,
        "surah_no": 112,
        "ayah_no_surah": 1,
        "arabic_annotation": {
            "categories": ["one", verse],
            "search_retrieval_fields": {"keywords_ar": [verse], "context_window": verse},
            "semantic_tags_entities": {"semantic_tags": ["two"]},
        },
    }

    row, left_out = annotation_row(record, SHA, [search_copy(verse), ""])

    assert left_out == 3
    assert row["categories"] == ["one"]
    assert row["keywords_ar"] == []
    assert row["annotation"]["search_retrieval_fields"] == {"keywords_ar": []}
    assert row["semantic_tags"] == ["two"]


def test_odd_shapes_become_empty_or_single_lists():
    record = {
        "ayah_id": 1,
        "surah_no": 1,
        "ayah_no_surah": 1,
        "arabic_annotation": {
            "islamic_cognitive_dimension": "not a dict",
            "categories": "one",
            "search_retrieval_fields": {"key_concepts": [" a ", "", 3], "keywords_ar": None},
        },
    }

    row, left_out = annotation_row(record, SHA, [])

    assert left_out == 0
    assert row["islamic_domain"] is None
    assert row["categories"] == ["one"]
    assert row["key_concepts"] == ["a"]
    assert row["keywords_ar"] == []
    assert row["semantic_tags"] == []
    assert row["annotation_model"] is None
    assert set(row["annotation"]) == {
        "islamic_cognitive_dimension",
        "categories",
        "search_retrieval_fields",
    }


def test_a_corpus_that_is_not_a_list_or_repeats_a_verse_is_refused():
    records = load_json("quran-annotations.json")

    with pytest.raises(AnnotationImportError, match="not a list"):
        check_records({"records": records})
    with pytest.raises(AnnotationImportError, match="a verse twice"):
        check_records([records[0], records[0]])


async def test_annotations_of_verses_not_in_the_store_are_refused(db_session):
    with pytest.raises(
        AnnotationImportError, match=r"7 annotated verses are not in the store \(1:1"
    ):
        await import_annotations(db_session, load_json("quran-annotations.json"), SHA)


async def test_importing_again_replaces_and_an_empty_corpus_empties(quran_session):
    raw = load_json("quran-annotations.json")
    await import_annotations(quran_session, raw, SHA)
    await import_annotations(quran_session, raw, SHA)
    count = await quran_session.scalar(select(func.count()).select_from(QuranAnnotation))

    await import_annotations(quran_session, [], SHA)

    assert count == len(raw)
    assert await quran_session.scalar(select(func.count()).select_from(QuranAnnotation)) == 0
    assert await quran_session.scalar(select(func.count()).select_from(QuranVerse)) > 0


async def test_the_annotations_step_checks_the_file_before_importing(
    tmp_path, scripture_maker, monkeypatch, capsys
):
    async with scripture_maker() as session, session.begin():
        await store_quran(session)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    argv = ["annotations", "--corpus-dir", str(corpus)]

    missing = await import_scripture.run(argv, sessionmaker=scripture_maker)
    shutil.copy(fixture_path("quran-annotations.json"), corpus / "quran-annotations.json")
    tampered = await import_scripture.run(argv, sessionmaker=scripture_maker)
    monkeypatch.setattr(
        import_scripture, "ANNOTATIONS_SHA256", file_sha256(corpus / "quran-annotations.json")
    )
    done = await import_scripture.run(argv, sessionmaker=scripture_maker)

    captured = capsys.readouterr()
    assert (missing, tampered, done) == (1, 1, 0)
    assert "quran-annotations.json is missing" in captured.err
    assert "has sha256" in captured.err
    assert "annotations: 7 verses annotated," in captured.out
    assert "strings repeating their verse left out" in captured.out
