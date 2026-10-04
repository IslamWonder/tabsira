"""The nine books: numbers as their dataset writes them, text exactly as given, never overwritten."""

from __future__ import annotations

import csv
import io
import json

import httpx
import pytest
from sqlalchemy import func, select

from src.cli import import_scripture
from src.models import Hadith, HadithCollection, HadithSearch, ScriptureAudit
from src.scripture import hadith as hadith_store
from src.scripture.guard import WritePurpose, allow_scripture_writes
from src.scripture.hadith import (
    COLLECTIONS,
    HadithImportError,
    ensure_source_file,
    import_collection,
    parse_open_hadith_csv,
    parse_source,
)
from src.scripture.text import search_copy, sha256_hex
from tests.scripture.fake_http import FakeQuranpedia, hadith_routes
from tests.scripture.fixtures import (
    HADITH_FIXTURES,
    cache_hadith_fixtures,
    fixture_path,
    fixture_sources,
    load_json,
)

RLM = chr(0x200F)


def _source(slug: str):
    return next(source for source in fixture_sources() if source.slug == slug)


def _parsed(slug: str):
    return parse_source(_source(slug), fixture_path(HADITH_FIXTURES[slug]).read_bytes())


def _csv_rows(name: str) -> list[list[str]]:
    with fixture_path(name).open(newline="", encoding="utf-8") as handle:
        return list(csv.reader(handle))


async def _import(session, slug: str):
    await allow_scripture_writes(session, WritePurpose.IMPORT)
    return await import_collection(session, _source(slug), _parsed(slug))


def test_the_nine_books_are_pinned_to_one_commit_and_one_hash_each():
    assert [source.slug for source in COLLECTIONS] == [
        "bukhari",
        "muslim",
        "abudawud",
        "tirmidhi",
        "nasai",
        "ibnmajah",
        "malik",
        "ahmad",
        "darimi",
    ]
    assert {source.licence for source in COLLECTIONS[:7]} == {"Unlicense"}
    assert {source.licence for source in COLLECTIONS[7:]} == {"ODbL-1.0"}
    for source in COLLECTIONS:
        assert source.commit in source.url
        assert len(source.sha256) == 64
    assert COLLECTIONS[0].url == (
        "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@"
        "df57907be35291c91ad6a6691180e22ca9920784/editions/ara-bukhari.json"
    )
    assert COLLECTIONS[7].url.startswith(
        "https://raw.githubusercontent.com/mhashim6/Open-Hadith-Data/1515f6cb"
    )
    assert COLLECTIONS[7].url.endswith("musnad_ahmad_ibn-hanbal_ahadith_mushakkala.utf8.csv")


def test_fawazahmed0_numbers_stay_as_written_and_empty_texts_are_skipped():
    raw = load_json("ara-bukhari.json")
    parsed = _parsed("bukhari")
    by_number = {record.number: record for record in parsed.records}

    empty = [str(h["hadithnumber"]) for h in raw["hadiths"] if not h["text"].strip()]
    assert parsed.skipped_empty == empty == ["5710"]
    assert set(by_number) == {"1", "8", "402.2", "1032"}
    hadith = by_number["1032"]
    source = next(h for h in raw["hadiths"] if h["hadithnumber"] == 1032)
    assert hadith.text == source["text"]
    assert (hadith.arabic_number, hadith.book_number, hadith.number_in_book) == ("1032", 15, 27)
    assert hadith.book_name == raw["metadata"]["sections"]["15"]
    assert hadith.grades == []


def test_muslim_keeps_abd_al_baqi_numbers_and_abu_dawud_keeps_its_grades():
    muslim = {record.number: record for record in _parsed("muslim").records}
    abudawud = _parsed("abudawud").records[0]

    assert muslim["3"].arabic_number is None
    assert muslim["3"].book_number == 0
    assert muslim["113"].arabic_number == "16.03"
    assert abudawud.grades == load_json("ara-abudawud.json")["hadiths"][0]["grades"]


def test_open_hadith_data_text_keeps_its_right_to_left_marks():
    rows = _csv_rows("musnad-ahmad.csv")
    parsed = _parsed("ahmad")

    assert [record.number for record in parsed.records] == [row[0] for row in rows]
    assert [record.text for record in parsed.records] == [row[1] for row in rows]
    assert RLM in parsed.records[0].text
    assert parsed.records[0].text.startswith(RLM + " " + RLM)
    assert parsed.records[0].grades is None


def test_malformed_or_ambiguous_sources_are_refused():
    with pytest.raises(HadithImportError, match="unexpected Open-Hadith-Data row"):
        parse_open_hadith_csv(b'"x","text"\n')
    with pytest.raises(HadithImportError, match="unexpected Open-Hadith-Data row"):
        parse_open_hadith_csv(b'"1"\n')
    assert parse_open_hadith_csv(b'"1"," "\n').skipped_empty == ["1"]
    with pytest.raises(HadithImportError, match="not well-formed CSV"):
        parse_open_hadith_csv(b'"1","a"b"\n')

    raw = load_json("ara-bukhari.json")
    raw["hadiths"].append(raw["hadiths"][1])
    with pytest.raises(HadithImportError, match="numbers two hadiths alike"):
        parse_source(_source("bukhari"), json.dumps(raw).encode())


async def test_hadiths_are_stored_exactly_with_their_hash_and_search_copy(db_session):
    report = await _import(db_session, "bukhari")

    rows = (await db_session.scalars(select(Hadith).order_by(Hadith.id))).all()
    folded = dict(
        (
            await db_session.execute(select(HadithSearch.hadith_id, HadithSearch.normalized_text))
        ).all()
    )
    source = {str(h["hadithnumber"]): h for h in load_json("ara-bukhari.json")["hadiths"]}
    collection = await db_session.get(HadithCollection, "bukhari")
    audit = (await db_session.scalars(select(ScriptureAudit))).one()

    assert (report.inserted, report.unchanged, report.skipped_empty) == (4, 0, 1)
    assert {row.number for row in rows} == {"1", "8", "402.2", "1032"}
    for row in rows:
        assert row.text == source[row.number]["text"]
        assert row.text_sha256 == sha256_hex(source[row.number]["text"])
        assert folded[row.id] == search_copy(row.text) != row.text
        assert row.informational_grades == []
        assert (row.source_dataset, row.source_version) == (
            "fawazahmed0/hadith-api",
            hadith_store.FAWAZ_COMMIT,
        )
    assert collection is not None
    assert (collection.name_ar, collection.licence, collection.display_order) == (
        "صحيح البخاري",
        "Unlicense",
        1,
    )
    assert collection.source_sha256 == _source("bukhari").sha256
    assert (audit.entity, audit.entity_key) == (
        "hadith_import",
        f"bukhari {hadith_store.FAWAZ_COMMIT}",
    )


async def test_importing_again_changes_nothing(db_session):
    await _import(db_session, "ahmad")
    before = (await db_session.execute(select(Hadith.id, Hadith.text_sha256))).all()

    report = await _import(db_session, "ahmad")

    assert (report.inserted, report.unchanged) == (0, 2)
    assert (await db_session.execute(select(Hadith.id, Hadith.text_sha256))).all() == before


async def test_a_source_that_would_change_a_stored_hadith_is_refused(db_session):
    await _import(db_session, "darimi")
    rows = _csv_rows("sunan-al-darimi.csv")
    rows[0][1] = rows[1][1]
    buffer = io.StringIO()
    csv.writer(buffer, quoting=csv.QUOTE_ALL).writerows(rows)

    with pytest.raises(HadithImportError, match=r"changes stored hadiths \(1\)"):
        await import_collection(
            db_session, _source("darimi"), parse_open_hadith_csv(buffer.getvalue().encode())
        )


async def test_a_pinned_file_is_downloaded_once_and_verified(tmp_path):
    source = _source("muslim")
    fake = FakeQuranpedia(hadith_routes())
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))

    first = await ensure_source_file(http, tmp_path, source)
    second = await ensure_source_file(http, tmp_path, source)

    assert first == second == tmp_path / "hadith" / "ara-muslim.json"
    assert first.read_bytes() == fixture_path("ara-muslim.json").read_bytes()
    assert len(fake.requests) == 1


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (httpx.Response(404), "answered 404"),
        (httpx.Response(200, content=b"other bytes"), "has sha256"),
    ],
)
async def test_a_pinned_file_that_cannot_be_had_whole_is_refused(tmp_path, answer, message):
    source = _source("ahmad")
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: answer))

    with pytest.raises(Exception, match=message):
        await ensure_source_file(http, tmp_path, source)

    assert not source.cache_path(tmp_path).exists()


async def test_a_network_failure_is_reported(tmp_path):
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(fail))

    with pytest.raises(HadithImportError, match="failed: ConnectError"):
        await ensure_source_file(http, tmp_path, _source("ahmad"))


async def test_the_hadith_step_imports_every_verified_book(
    tmp_path, scripture_maker, monkeypatch, capsys
):
    monkeypatch.setattr(import_scripture.hadith_store, "COLLECTIONS", fixture_sources())
    argv = ["hadith", "--cache-dir", str(tmp_path)]

    missing = await import_scripture.run(argv, sessionmaker=scripture_maker)
    cache_hadith_fixtures(tmp_path)
    done = await import_scripture.run(argv, sessionmaker=scripture_maker)

    captured = capsys.readouterr()
    assert (missing, done) == (1, 0)
    assert "ara-bukhari.json is missing" in captured.err
    assert "hadith: bukhari, 4 inserted, 0 unchanged, 1 with an empty text" in captured.out
    assert "hadith: darimi, 2 inserted" in captured.out
    async with scripture_maker() as session:
        count = await session.scalar(select(func.count()).select_from(Hadith))
    assert count == 4 + 2 + 1 + 2 + 2
