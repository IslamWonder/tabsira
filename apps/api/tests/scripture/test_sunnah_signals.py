"""The enriched Sunnah file: repaired losslessly, linked by text, stored as model-written signals."""

from __future__ import annotations

import shutil

import pytest
from sqlalchemy import func, select

from src.cli import import_scripture
from src.models import Hadith, HadithSignal
from src.scripture.files import file_sha256
from src.scripture.sunnah import (
    SunnahImportError,
    TrigramMatcher,
    _best_per_collection,
    cited_collections,
    import_signals,
    main_narration,
    repair,
    repair_text,
    require_round_trip,
)
from tests.scripture.fixtures import (
    cache_hadith_fixtures,
    fixture_path,
    fixture_sources,
    load_json,
    store_hadiths,
)


def _records() -> list[dict]:
    return repair(load_json("sunnah-enriched.json")["results"])


def test_the_cp720_repair_is_lossless_for_every_string():
    raw = load_json("sunnah-enriched.json")["results"]
    repaired = repair(raw)

    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)
        elif isinstance(value, dict):
            for item in value.values():
                yield from strings(item)

    pairs = list(zip(strings(raw), strings(repaired), strict=True))
    assert pairs
    for original, fixed in pairs:
        assert fixed.encode("utf-8").decode("cp720") == original
    assert repaired[0]["id"] == raw[0]["id"]
    assert any(0x0600 <= ord(char) <= 0x06FF for char in repaired[0]["summary"])
    assert repair(3) == 3


def test_text_that_is_not_cp720_mojibake_is_refused():
    with pytest.raises(SunnahImportError, match="not cp720 mojibake"):
        repair_text(chr(0x20AC))
    with pytest.raises(SunnahImportError, match="not lossless"):
        require_round_trip("a", "b")


def test_the_main_narration_drops_codes_variants_references_and_footnotes():
    record = next(r for r in _records() if r["id"] == "1")
    narration = main_narration(record["original_text"])

    assert not narration.lstrip().startswith("(")
    assert "[" not in narration
    assert narration.strip() in record["original_text"]
    assert main_narration("(x) a (1) b ! c [d 1]").split() == ["a", "b"]


def test_cited_books_come_from_the_leading_code_and_the_references():
    records = {record["id"]: record for record in _records()}

    assert cited_collections(records["1"]["original_text"]) == {"bukhari", "muslim"}
    assert cited_collections(records["1535"]["original_text"]) == {"bukhari"}
    assert cited_collections(records["3"]["original_text"]) == set()
    assert cited_collections("(خـ) x [حم 5 و جه 7]") == {
        "bukhari",
        "ahmad",
        "ibnmajah",
    }


def test_an_unknown_leading_code_cites_nothing_and_each_book_keeps_its_best_match():
    from src.scripture.sunnah import _best_per_collection

    about = {1: ("muslim", "9", 2), 2: ("muslim", "10", 2), 3: ("ahmad", "5", 8)}

    ranked = _best_per_collection([(3, 0.95), (1, 0.9), (2, 0.8)], about, {"muslim"})

    assert cited_collections("(x) y") == set()
    assert [(m["collection"], m["number"]) for m in ranked] == [("muslim", "9"), ("ahmad", "5")]


def test_the_matcher_weighs_rare_grams_and_ignores_common_ones_for_candidates(monkeypatch):
    from src.scripture import sunnah

    matcher = TrigramMatcher({"q": {("a", "b", "c"), ("b", "c", "d"), ("x", "y", "z")}})
    matcher.add(1, "a b c d")
    matcher.add(2, "a b c")
    matcher.add(3, "q r s")

    found = matcher.match("q", 0.5)

    assert [document for document, _ in found] == [1]
    assert found[0][1] == pytest.approx(
        (matcher._idf(("a", "b", "c")) + matcher._idf(("b", "c", "d")))
        / sum(matcher._idf(g) for g in matcher.queries["q"])
    )
    monkeypatch.setattr(sunnah, "CANDIDATE_MAX_DF", 0)
    assert matcher.match("q", 0.0) == []


def test_candidates_that_cannot_reach_the_threshold_are_dropped(monkeypatch):
    from src.scripture import sunnah

    monkeypatch.setattr(sunnah, "CANDIDATE_MAX_DF", 1)
    rare, other_rare, common, common_too = (
        ("a", "b", "c"),
        ("d", "e", "f"),
        ("g", "h", "i"),
        ("j", "k", "l"),
    )
    matcher = TrigramMatcher({"q": {rare, other_rare, common, common_too}})
    matcher.add(1, "a b c g h i")
    matcher.add(2, "d e f")
    matcher.add(3, "g h i j k l")
    matcher.add(4, "j k l")

    assert [document for document, _ in matcher.match("q", 0.45)] == [1]
    assert matcher.match("q", 0.99) == []


async def test_records_are_linked_to_the_hadith_their_text_matches(db_session):
    await store_hadiths(db_session)

    report = await import_signals(db_session, _records(), model="m", source_sha256="b" * 64)

    signals = {
        row.source_record_id: row for row in (await db_session.scalars(select(HadithSignal))).all()
    }
    numbers = dict((await db_session.execute(select(Hadith.id, Hadith.number))).all())
    assert (report.records, report.linked) == (4, 2)
    assert numbers[signals["1"].hadith_id] == "8"
    assert numbers[signals["1535"].hadith_id] == "1032"
    assert signals["1"].matches[0]["collection"] == "bukhari"
    assert signals["1"].match_coverage == signals["1"].matches[0]["coverage"] >= 0.5
    # Each match says whether the compiler cites its book (decision 58); record 1 cites خ and م.
    assert signals["1"].matches[0]["cited"] is True
    assert numbers[signals["1535"].hadith_id] == "1032"
    assert signals["1535"].matches[0]["cited"] is True
    assert signals["3"].hadith_id is None
    assert signals["3"].matches == []
    assert signals["617"].hadith_id is None


def test_a_book_the_compiler_does_not_cite_is_marked_so_and_ranks_after_a_cited_one():
    about = {1: ("muslim", "16", 1), 2: ("abudawud", "40", 2)}

    matches = _best_per_collection([(2, 0.97), (1, 0.81)], about, {"muslim"})

    assert [(m["collection"], m["cited"]) for m in matches] == [
        ("muslim", True),
        ("abudawud", False),
    ]


async def test_signals_keep_what_the_model_wrote_under_names_that_say_so(db_session):
    await store_hadiths(db_session)
    records = {record["id"]: record for record in _records()}

    await import_signals(db_session, list(records.values()), model="m", source_sha256="b" * 64)

    row = (
        await db_session.scalars(select(HadithSignal).where(HadithSignal.source_record_id == "1"))
    ).one()
    record = records["1"]
    assert row.model_written_summary == record["summary"]
    assert row.model_written_rephrase == record["modern_rephrase"]
    assert (row.domain, row.category_new) == (record["domain"], record["category_new"])
    assert row.semantic_tags == record["semantic_tags"]
    assert row.key_concepts == record["key_concepts"]
    assert row.topics_for_retrieval == record["topics_for_retrieval"]
    assert row.sciences == record["sciences"]
    assert row.generated_by_model == "m"
    columns = set(HadithSignal.__table__.columns.keys())
    assert not {"text", "summary", "modern_rephrase", "original_text"} & columns


async def test_importing_again_replaces_the_signals_and_a_repeated_id_is_refused(db_session):
    await store_hadiths(db_session)
    await import_signals(db_session, _records(), model="m", source_sha256="b" * 64)
    await import_signals(db_session, _records(), model="m", source_sha256="b" * 64)

    assert await db_session.scalar(select(func.count()).select_from(HadithSignal)) == 4
    with pytest.raises(SunnahImportError, match="record id twice"):
        await import_signals(db_session, _records() * 2, model="m", source_sha256="b" * 64)
    await import_signals(db_session, [], model="m", source_sha256="b" * 64)
    assert await db_session.scalar(select(func.count()).select_from(HadithSignal)) == 0


async def test_the_signals_step_checks_repairs_and_links(
    tmp_path, scripture_maker, monkeypatch, capsys
):
    monkeypatch.setattr(import_scripture.hadith_store, "COLLECTIONS", fixture_sources())
    cache_hadith_fixtures(tmp_path)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    shutil.copy(fixture_path("sunnah-enriched.json"), corpus / "sunnah-enriched.json")
    argv = ["--cache-dir", str(tmp_path), "--corpus-dir", str(corpus)]

    tampered = await import_scripture.run(["signals", *argv], sessionmaker=scripture_maker)
    monkeypatch.setattr(
        import_scripture, "SUNNAH_SHA256", file_sha256(corpus / "sunnah-enriched.json")
    )
    done = await import_scripture.run(["hadith", "signals", *argv], sessionmaker=scripture_maker)

    captured = capsys.readouterr()
    assert (tampered, done) == (1, 0)
    assert "sunnah-enriched.json has sha256" in captured.err
    assert "signals: 4 records repaired losslessly, 2 linked to a hadith, 2 without a match" in (
        captured.out
    )
    async with scripture_maker() as session:
        model = await session.scalar(select(HadithSignal.generated_by_model).limit(1))
    assert model == "gpt-5-mini-2025-08-07"
