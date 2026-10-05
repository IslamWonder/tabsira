"""The read API: every displayed text is the stored one, byte for byte, and matches its hash."""

from __future__ import annotations

import csv
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import AsyncClient

from src.database import get_db
from src.models import HadithClassification
from src.scripture.annotations import import_annotations
from src.scripture.rulings import RulingInput, find_hadith, record_ruling
from src.scripture.sunnah import import_signals, repair
from src.scripture.text import sha256_hex
from tests.helpers import client_for
from tests.scripture.fixtures import (
    enrich_hadith,
    fixture_path,
    load_json,
    store_hadiths,
    store_quran,
)

RLM = chr(0x200F)


@pytest_asyncio.fixture
async def api(app, db_session) -> AsyncIterator[AsyncClient]:
    """A client whose requests read the test session, holding the fixture verses and hadiths."""
    await store_quran(db_session)
    await store_hadiths(db_session)

    async def session_override() -> AsyncIterator:
        yield db_session

    app.dependency_overrides[get_db] = session_override
    try:
        async with client_for(app) as http:
            yield http
    finally:
        app.dependency_overrides.pop(get_db)


async def test_every_stored_verse_is_served_exactly_with_its_hash(api):
    surahs = load_json("quranpedia-mushafs-2.json")["data"]["surahs"]

    for surah in surahs:
        for verse in surah["ayahs"]:
            response = await api.get(f"/scripture/quran/{surah['id']}/{verse['number']}")
            body = response.json()

            assert response.status_code == 200
            assert body["text"] == verse["text"]
            assert body["sha256"] == sha256_hex(body["text"]) == sha256_hex(verse["text"])
            assert body["surah_name"] == surah["name"]
            assert body["source"]["quranpedia_ayah_id"] == verse["id"]


async def test_a_verse_carries_its_source_version_link_and_honest_status(api):
    body = (await api.get("/scripture/quran/30/50")).json()

    assert body["source"] == {
        "name": "quranpedia.net",
        "url": "https://quranpedia.net",
        "mushaf_id": 2,
        "mushaf_name": "مصحف حفص نسخة نصية",
        "quranpedia_ayah_id": 65709,
        "version": "dump:2026-10-03",
        "dump_version": "2026-10-03",
        "last_sync_at": None,
    }
    assert body["links"] == {"quranpedia": "https://quranpedia.net/surah/2/30#verse-65709"}
    assert (body["page"], body["juz"], body["status"]) == (409, 21, "verified_cached")
    assert "normalized_text" not in body


async def test_model_written_annotations_never_reach_the_verse_answer(api, db_session):
    await import_annotations(db_session, load_json("quran-annotations.json"), "a" * 64)
    annotation = next(
        r["arabic_annotation"]
        for r in load_json("quran-annotations.json")
        if (r["surah_no"], r["ayah_no_surah"]) == (30, 50)
    )

    response = await api.get("/scripture/quran/30/50")

    assert response.status_code == 200
    written = [
        annotation["search_retrieval_fields"]["context_window"],
        *annotation["related_research_fields"],
    ]
    for sentence in written:
        assert sentence not in response.text
    assert not {"annotation", "keywords_ar", "categories"} & set(response.json())


async def test_a_missing_or_impossible_verse_is_refused(api):
    missing = await api.get("/scripture/quran/2/3")
    impossible = await api.get("/scripture/quran/115/1")

    assert (missing.status_code, missing.json()["error"]) == (404, "NOT_FOUND")
    assert impossible.status_code == 422


async def test_every_stored_hadith_is_served_exactly_with_its_hash(api):
    books = {
        "bukhari": load_json("ara-bukhari.json")["hadiths"],
        "muslim": load_json("ara-muslim.json")["hadiths"],
        "abudawud": load_json("ara-abudawud.json")["hadiths"],
    }
    served = 0
    for collection, hadiths in books.items():
        for item in hadiths:
            if not item["text"].strip():
                continue
            response = await api.get(f"/scripture/hadith/{collection}/{item['hadithnumber']}")
            body = response.json()

            assert response.status_code == 200
            assert body["text"] == item["text"]
            assert body["sha256"] == sha256_hex(body["text"]) == sha256_hex(item["text"])
            assert (
                "".join(body["text"][s["start"] : s["end"]] for s in body["spans"]) == item["text"]
            )
            assert body["informational_grades"] == item["grades"]
            served += 1
    for name, collection in (("musnad-ahmad.csv", "ahmad"), ("sunan-al-darimi.csv", "darimi")):
        with fixture_path(name).open(newline="", encoding="utf-8") as handle:
            for number, text in csv.reader(handle):
                body = (await api.get(f"/scripture/hadith/{collection}/{number}")).json()
                assert body["text"] == text
                assert RLM in body["text"]
                assert body["sha256"] == sha256_hex(text)
                assert (body["chapter"], body["informational_grades"]) == (None, None)
                served += 1
    assert served == 11


async def test_a_hadith_carries_its_book_spans_and_status_and_no_ruling_or_link(api):
    body = (await api.get("/scripture/hadith/bukhari/1032")).json()

    assert body["collection"]["slug"] == "bukhari"
    assert body["collection"]["name_ar"] == "صحيح البخاري"
    assert body["collection"]["licence"] == "Unlicense"
    assert body["collection"]["source_dataset"] == "fawazahmed0/hadith-api"
    assert (body["number"], body["arabic_number"]) == ("1032", "1032")
    assert body["chapter"]["book_number"] == 15
    assert [span["role"] for span in body["spans"]] == ["chain", "body", "words", "tail"]
    assert body["status"] == "local_corpus"
    for field in ("ruling", "eligible", "links"):
        assert field not in body


async def test_a_decimal_number_is_found_as_the_dataset_writes_it(api):
    response = await api.get("/scripture/hadith/bukhari/402.2")

    assert response.status_code == 200
    assert response.json()["number"] == "402.2"


async def test_a_hadith_with_no_ruling_is_shown_whether_or_not_the_file_enriches_it(
    api, db_session
):
    plain = await api.get("/scripture/hadith/bukhari/1032")
    hadith = await find_hadith(db_session, "bukhari", "1032")
    assert hadith is not None
    await enrich_hadith(db_session, hadith.id)
    enriched = await api.get("/scripture/hadith/bukhari/1032")

    assert (plain.status_code, enriched.status_code) == (200, 200)
    assert enriched.json() == plain.json()


def _ruling(classification: HadithClassification) -> RulingInput:
    return RulingInput(
        ruling_text="[حكم]",
        scholar="s",
        source_book="b",
        page="1",
        dorar_url="https://dorar.net/h/x",
        classification=classification,
        editor_name="private editor",
    )


async def test_an_editor_ruling_of_sahih_leaves_the_hadith_shown_without_the_ruling(
    api, db_session
):
    hadith = await find_hadith(db_session, "bukhari", "1032")
    assert hadith is not None
    await record_ruling(db_session, hadith.id, _ruling(HadithClassification.SAHIH))

    response = await api.get("/scripture/hadith/bukhari/1032")

    assert response.status_code == 200
    assert "ruling" not in response.json()
    assert "private editor" not in response.text


async def test_a_hadith_an_editor_ruled_weak_is_not_found(api, db_session):
    hadith = await find_hadith(db_session, "bukhari", "1032")
    assert hadith is not None
    await record_ruling(db_session, hadith.id, _ruling(HadithClassification.DAIF))

    response = await api.get("/scripture/hadith/bukhari/1032")

    assert (response.status_code, response.json()["error"]) == (404, "NOT_FOUND")


async def test_model_written_signals_never_reach_the_hadith_answer(api, db_session):
    records = repair(load_json("sunnah-enriched.json")["results"])
    await import_signals(db_session, records, model="m", source_sha256="b" * 64)
    linked = next(record for record in records if record["id"] == "1535")

    response = await api.get("/scripture/hadith/bukhari/1032")

    assert response.status_code == 200
    for field in ("summary", "modern_rephrase"):
        assert linked[field] not in response.text
        assert field not in response.json()


async def test_a_missing_or_malformed_hadith_is_refused(api):
    missing = await api.get("/scripture/hadith/bukhari/99999")
    malformed = await api.get("/scripture/hadith/bukhari/1;2")
    unknown_book = await api.get("/scripture/hadith/Bukhari/1")

    assert (missing.status_code, missing.json()["error"]) == (404, "NOT_FOUND")
    assert malformed.status_code == unknown_book.status_code == 422


async def test_the_routes_are_in_the_published_contract(api):
    paths = (await api.get("/openapi.json")).json()["paths"]

    assert "/scripture/quran/{surah}/{ayah}" in paths
    assert "/scripture/hadith/{collection}/{number}" in paths
