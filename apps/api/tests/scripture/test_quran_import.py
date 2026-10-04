"""Importing quranpedia mushaf 2: every verse byte for byte, with its hash, and corrections kept."""

from __future__ import annotations

import copy
import gzip
import json
from datetime import date

import pytest
from sqlalchemy import func, select, text, update

from src.models import (
    QuranSurah,
    QuranVerse,
    QuranVerseHistory,
    QuranVerseSearch,
    ScriptureAudit,
    ScriptureSyncState,
)
from src.scripture import quran
from src.scripture.guard import WritePurpose, allow_scripture_writes
from src.scripture.quran import (
    QuranImportError,
    import_quran,
    load_json_file,
    parse_mushaf,
    parse_surahs,
)
from src.scripture.text import search_copy, sha256_hex
from tests.scripture.fixtures import fixture_path, load_json, verse_text


def _fixture_verses() -> list[dict]:
    return [
        ayah
        for surah in load_json("quranpedia-mushafs-2.json")["data"]["surahs"]
        for ayah in surah["ayahs"]
    ]


def _dump_with(surah: int, ayah: int, **fields) -> dict:
    raw = copy.deepcopy(load_json("quranpedia-mushafs-2.json"))
    for entry in raw["data"]["surahs"]:
        for verse in entry["ayahs"]:
            if (entry["id"], verse["number"]) == (surah, ayah):
                verse.update(fields)
    return raw


async def _import(session, raw: dict, *, version: str | None = None):
    if version:
        raw = {**raw, "license": {**raw["license"], "version": version}}
    await allow_scripture_writes(session, WritePurpose.IMPORT)
    return await import_quran(
        session,
        parse_mushaf(raw),
        parse_surahs(load_json("quranpedia-surahs.json")),
        dump_sha256="1" * 64,
        source="test dump",
    )


async def test_every_verse_is_stored_exactly_as_the_dump_gives_it(db_session):
    report = await _import(db_session, load_json("quranpedia-mushafs-2.json"))

    stored = {
        (row.surah, row.ayah): row for row in (await db_session.scalars(select(QuranVerse))).all()
    }
    verses = _fixture_verses()
    assert report.inserted == len(verses) == len(stored)
    for ayah in verses:
        row = stored[(int(ayah["surah"]), ayah["number"])]
        assert row.text == ayah["text"]
        assert row.text_sha256 == sha256_hex(ayah["text"])
        assert row.quranpedia_ayah_id == ayah["id"]
        assert (row.page, row.juz, row.mushaf_id) == (ayah["page_number"], ayah["juz"], 2)
        assert row.source_version == "dump:2026-10-03"


async def test_the_search_copy_is_stored_apart_and_folded(db_session):
    await _import(db_session, load_json("quranpedia-mushafs-2.json"))

    rows = (
        await db_session.execute(
            select(QuranVerse.text, QuranVerseSearch.normalized_text).join(
                QuranVerseSearch, QuranVerseSearch.verse_id == QuranVerse.id
            )
        )
    ).all()

    assert len(rows) == len(_fixture_verses())
    for display, folded in rows:
        assert folded == search_copy(display) != display
    assert "normalized_text" not in QuranVerse.__table__.columns


async def test_surahs_carry_the_mushaf_name_and_quranpedia_facts(db_session):
    await _import(db_session, load_json("quranpedia-mushafs-2.json"))
    information = {
        entry["surah"]: entry["information"]
        for entry in load_json("quranpedia-surahs.json")["data"]
    }
    names = {
        entry["id"]: entry["name"]
        for entry in load_json("quranpedia-mushafs-2.json")["data"]["surahs"]
    }

    surah = await db_session.get(QuranSurah, 30)

    assert surah is not None
    assert surah.name_ar == names[30]
    assert surah.revelation_place == information[30]["surah_type"]["value"]
    assert surah.revelation_order == int(information[30]["descent"]["value"])
    assert surah.words_count == int(information[30]["words_count"]["value"])
    kufan = [
        c["value"] for c in information[30]["ayahs_count"] if c["title"] == quran.KUFAN_COUNT_TITLE
    ]
    assert surah.ayah_count == kufan[0] == 60


async def test_an_import_is_audited_and_starts_the_changes_feed_from_its_version(db_session):
    await _import(db_session, load_json("quranpedia-mushafs-2.json"))

    audit = (await db_session.scalars(select(ScriptureAudit))).one()
    state = await db_session.get(ScriptureSyncState, quran.SYNC_SOURCE)

    assert (audit.entity, audit.action, audit.new_sha256) == ("quran_import", "import", "1" * 64)
    assert audit.entity_key == "mushaf-2 2026-10-03"
    assert state is not None
    assert (state.synced_through, state.dump_version) == (date(2026, 10, 3), "2026-10-03")


async def test_importing_the_same_dump_again_changes_no_verse(db_session):
    await _import(db_session, load_json("quranpedia-mushafs-2.json"))
    before = (await db_session.execute(select(QuranVerse.id, QuranVerse.text_sha256))).all()

    report = await _import(db_session, load_json("quranpedia-mushafs-2.json"))

    assert (report.inserted, report.corrected, report.metadata_updated) == (0, 0, 0)
    assert report.unchanged == len(_fixture_verses())
    assert (await db_session.execute(select(QuranVerse.id, QuranVerse.text_sha256))).all() == before
    assert await db_session.scalar(select(func.count()).select_from(QuranVerseHistory)) == 0


async def test_a_newer_dump_with_another_text_keeps_the_old_one_in_history(db_session):
    earlier = load_json("kfgqpc-v13-30-50.json")["text"]
    await _import(db_session, _dump_with(30, 50, text=earlier), version="2026-10-01")

    report = await _import(db_session, load_json("quranpedia-mushafs-2.json"))

    verse = (await db_session.scalars(select(QuranVerse).where(QuranVerse.ayah == 50))).one()
    history = (await db_session.scalars(select(QuranVerseHistory))).one()
    correction = (
        await db_session.scalars(select(ScriptureAudit).where(ScriptureAudit.action == "correct"))
    ).one()
    folded = await db_session.scalar(
        select(QuranVerseSearch.normalized_text).where(QuranVerseSearch.verse_id == verse.id)
    )
    state = await db_session.get(ScriptureSyncState, quran.SYNC_SOURCE)

    assert report.corrected == 1
    assert (verse.text, verse.source_version) == (verse_text(30, 50), "dump:2026-10-03")
    assert verse.text_sha256 == sha256_hex(verse_text(30, 50))
    assert (history.text, history.text_sha256) == (earlier, sha256_hex(earlier))
    assert (history.source_version, history.replaced_by_version) == (
        "dump:2026-10-01",
        "dump:2026-10-03",
    )
    assert (correction.entity_key, correction.old_sha256) == ("30:50", sha256_hex(earlier))
    assert correction.new_sha256 == verse.text_sha256
    assert folded == search_copy(verse_text(30, 50))
    assert state is not None
    assert state.synced_through == date(2026, 10, 3)


async def test_new_page_facts_are_taken_without_touching_the_text(db_session):
    await _import(db_session, load_json("quranpedia-mushafs-2.json"))

    report = await _import(db_session, _dump_with(30, 50, page_number=410))

    assert report.metadata_updated == 1
    verse = (await db_session.scalars(select(QuranVerse).where(QuranVerse.ayah == 50))).one()
    assert (verse.page, verse.text) == (410, verse_text(30, 50))


async def test_an_older_dump_does_not_move_the_changes_feed_back(db_session):
    await _import(db_session, load_json("quranpedia-mushafs-2.json"))
    await db_session.execute(update(ScriptureSyncState).values(synced_through=date(2026, 10, 20)))

    await _import(db_session, load_json("quranpedia-mushafs-2.json"), version="2026-10-02")

    state = await db_session.get(ScriptureSyncState, quran.SYNC_SOURCE)
    await db_session.refresh(state)
    assert state.synced_through == date(2026, 10, 20)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda raw: raw["data"].update(id=1), "expected the dump of mushaf 2"),
        (lambda raw: raw.update(schema="/v1/mushafs/1"), "expected the dump of mushaf 2"),
        (
            lambda raw: raw["data"]["surahs"][0]["ayahs"].append(
                raw["data"]["surahs"][0]["ayahs"][0]
            ),
            "repeated",
        ),
        (lambda raw: raw["data"]["surahs"][0]["ayahs"][0].update(surah="2"), "misplaced"),
        (lambda raw: raw["data"]["surahs"][0]["ayahs"][0].update(text=""), "empty"),
    ],
)
def test_a_dump_that_is_not_mushaf_2_or_not_well_formed_is_refused(change, message):
    raw = copy.deepcopy(load_json("quranpedia-mushafs-2.json"))
    change(raw)

    with pytest.raises(QuranImportError, match=message):
        parse_mushaf(raw)


async def test_missing_surah_facts_or_a_version_that_is_no_date_are_refused(db_session):
    await allow_scripture_writes(db_session, WritePurpose.IMPORT)
    mushaf = parse_mushaf(load_json("quranpedia-mushafs-2.json"))
    information = load_json("quranpedia-surahs.json")
    without_30 = {**information, "data": [e for e in information["data"] if e["surah"] != 30]}
    without_kufan = copy.deepcopy(information)
    for entry in without_kufan["data"]:
        entry["information"]["ayahs_count"] = entry["information"]["ayahs_count"][:1]
    bad_version = parse_mushaf(
        {**load_json("quranpedia-mushafs-2.json"), "license": {"version": "latest"}}
    )

    for dump, facts, message in (
        (mushaf, without_30, "no entry for surah 30"),
        (mushaf, without_kufan, "no Kufan verse count"),
        (bad_version, information, "is not a date"),
    ):
        with pytest.raises(QuranImportError, match=message):
            async with db_session.begin_nested():
                await import_quran(
                    db_session, dump, parse_surahs(facts), dump_sha256="0" * 64, source="x"
                )


def test_only_a_whole_mushaf_counts_as_complete(monkeypatch):
    dump = parse_mushaf(load_json("quranpedia-mushafs-2.json"))

    assert not dump.is_complete()
    monkeypatch.setattr(quran, "COMPLETE_SURAHS", len(dump.data.surahs))
    monkeypatch.setattr(quran, "COMPLETE_VERSES", len(dump.verses()))
    assert dump.is_complete()


def test_dump_files_are_read_compressed_or_plain(tmp_path):
    plain = fixture_path("quranpedia-surahs.json")
    packed = tmp_path / "surahs.json.gz"
    packed.write_bytes(gzip.compress(plain.read_bytes()))

    assert load_json_file(packed) == load_json_file(plain) == json.loads(plain.read_text())


async def test_the_stored_hash_is_checked_by_the_database_on_every_verse(quran_session):
    mismatched = await quran_session.scalar(
        text(
            "SELECT count(*) FROM corpus.quran_verses "
            "WHERE text_sha256 <> encode(sha256(convert_to(text, 'UTF8')), 'hex')"
        )
    )

    assert mismatched == 0
