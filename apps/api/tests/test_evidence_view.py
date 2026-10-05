"""Scripture in a response: read from the store by reference, shown only while it is eligible."""

from __future__ import annotations

from src.models import HadithClassification
from src.scripture.rulings import RulingInput, find_hadith, record_ruling
from src.scripture.text import sha256_hex
from src.services.evidence_view import load_evidence
from tests.scripture.fixtures import enrich_hadith, hadith_text, verse_text


async def rule(db_session, number, classification):
    hadith = await find_hadith(db_session, "bukhari", number)
    await record_ruling(
        db_session,
        hadith.id,
        RulingInput(
            ruling_text=f"[{classification.value}]",
            scholar="s",
            source_book="b",
            page="1",
            dorar_url="https://dorar.net/h/x",
            classification=classification,
            editor_name="editor",
        ),
    )


async def test_no_references_cost_no_query(db_session):
    found = await load_evidence(db_session, [], [])

    assert (found.quran, found.hadith) == ({}, {})


async def test_a_verse_is_read_exactly_as_stored_with_its_stored_hash(db_session, scripture):
    found = await load_evidence(db_session, [(1, 1), (2, 49), (112, 4), (112, 4)], [])

    assert set(found.quran) == {(1, 1), (2, 49), (112, 4)}
    for (surah, ayah), verse in found.quran.items():
        assert verse.text == verse_text(surah, ayah)
        assert verse.sha256 == sha256_hex(verse.text)
        assert verse.verified is True


async def test_a_reference_the_store_does_not_hold_is_left_out_and_never_replaced(
    db_session, scripture
):
    found = await load_evidence(
        db_session, [(112, 1), (114, 6), (3, 3)], [("bukhari", "1"), ("tirmidhi", "5")]
    )

    assert set(found.quran) == {(112, 1)}
    assert set(found.hadith) == {("bukhari", "1")}


async def test_a_hadith_is_read_as_stored_with_no_ruling_or_link_attached(db_session, scripture):
    found = await load_evidence(db_session, [], [("bukhari", "1")])

    hadith = found.hadith[("bukhari", "1")]
    assert hadith.text == hadith_text("bukhari", 1)
    assert hadith.sha256 == sha256_hex(hadith.text)
    assert hadith.collection_name
    assert not hasattr(hadith, "classification")
    assert not hasattr(hadith, "verification_url")


async def test_an_unruled_hadith_is_shown_and_a_weak_one_is_not(db_session, scripture):
    # bukhari 8 is ضعيف; muslim 113 has no ruling, so it is shown as it is (decision 64).
    found = await load_evidence(db_session, [], [("bukhari", "8"), ("muslim", "113")])

    assert set(found.hadith) == {("muslim", "113")}
    hadith = found.hadith[("muslim", "113")]
    assert hadith.text == hadith_text("muslim", 113)
    assert hadith.sha256 == sha256_hex(hadith.text)


async def test_the_enriched_file_neither_shows_a_hadith_nor_rescues_a_ruled_out_one(
    db_session, scripture
):
    for collection, number in (("muslim", "113"), ("bukhari", "8")):
        stored = await find_hadith(db_session, collection, number)
        await enrich_hadith(db_session, stored.id, f"{collection}{number}")

    found = await load_evidence(db_session, [], [("bukhari", "8"), ("muslim", "113")])

    assert set(found.hadith) == {("muslim", "113")}


async def test_the_latest_ruling_decides_in_both_directions(db_session, scripture):
    await rule(db_session, "8", HadithClassification.HASAN)
    await rule(db_session, "1", HadithClassification.DISPUTED)

    found = await load_evidence(db_session, [], [("bukhari", "1"), ("bukhari", "8")])

    assert set(found.hadith) == {("bukhari", "8")}


async def test_hadith_references_the_store_does_not_hold_find_nothing(db_session, scripture):
    found = await load_evidence(db_session, [], [("tirmidhi", "5"), ("bukhari", "999999")])

    assert found.hadith == {}
