"""The world: a fixed map under fog, the places completions open, threads and treasures."""

from __future__ import annotations

import hashlib
import json

import pytest
from sqlalchemy import select

from src.models import EvidenceExposure, HadithClassification, Profile, Treasure, WorldPlace
from src.owner import Owner
from src.services.content import load_regions
from tests.scans.builders import insight_row, scan_row
from tests.scans.conftest import DATA, as_guest, make_account, rule, sign_in

EXTRA = json.loads((DATA / "extra-scripture.json").read_text(encoding="utf-8"))


async def kept(store, owner: Owner, **values) -> str:
    async with store() as db:
        scan = scan_row(owner, status="done")
        db.add(scan)
        await db.flush()
        row = insight_row(owner, scan_id=scan.id, **values)
        db.add(row)
        await db.commit()
        return str(row.id)


DEEPER = {"learning_unit_id": "T01_01", "quran_surah": 3, "quran_ayah": 190}


async def test_a_newcomer_sees_the_whole_map_under_fog(browser):
    response = await browser.get("/world")

    body = response.json()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert (body["version"], body["path_version"]) == ("1.0", "tabsira-masar-1.0")
    assert len(body["regions"]) == 16
    assert all(region["fog"] and region["place_id"] is None for region in body["regions"])
    assert (body["places"], body["relations"]) == ([], [])


async def test_completions_lift_the_fog_and_record_threads(browser, store, flow_settings):
    owner = await as_guest(browser, store, flow_settings)
    async with store() as db:
        scan = scan_row(owner, status="done")
        db.add(scan)
        await db.flush()
        rain = insight_row(owner, scan_id=scan.id)
        garden = insight_row(owner, scan_id=scan.id, learning_unit_id="T12_02")
        db.add_all([rain, garden])
        await db.commit()
    for insight in (rain, garden):
        await browser.post(f"/insights/{insight.id}/complete")

    body = (await browser.get("/world")).json()

    regions = {region["id"]: region for region in body["regions"]}
    assert not regions["T01"]["fog"]
    assert regions["T01"]["name"] == "واحة الغيث"
    assert regions["T01"]["domain_title"] == "العالم والنعم والتفكر"
    assert regions["T01"]["position"] == {"x": 0.3, "y": 0.78}
    assert [region_id for region_id, region in regions.items() if not region["fog"]] == [
        "T01",
        "T12",
    ]
    places = {place["region_id"]: place for place in body["places"]}
    assert places["T01"]["id"] == regions["T01"]["place_id"]
    assert [item["title"] for item in places["T01"]["insights"]] == ["الحياة في قطرة"]
    assert places["T01"]["treasure"] is None
    (relation,) = body["relations"]
    assert relation["reason"] == "same_scene"
    assert relation["reason_label"] == "من المشهد نفسه"
    assert relation["question"] == "كيف ترتبطان؟"
    assert set(relation["insight_ids"]) == {str(rain.id), str(garden.id)}


async def test_a_treasure_waits_for_a_return_then_shows_its_verified_text(
    browser, store, flow_settings, moving_clock
):
    owner = await as_guest(browser, store, flow_settings)
    insight_id = await kept(store, owner, **DEEPER)
    await browser.post(f"/insights/{insight_id}/complete")
    world = (await browser.get("/world")).json()
    place_id = world["places"][0]["id"]
    async with store() as db:
        from src.models import Treasure

        treasure_id = str((await db.scalars(select(Treasure.id))).one())

    early = await browser.post(f"/world/treasures/{treasure_id}/reveal")
    moving_clock.advance(hours=1)
    soon = (await browser.post(f"/world/places/{place_id}/visit")).json()
    moving_clock.advance(hours=12)
    back = (await browser.post(f"/world/places/{place_id}/visit")).json()
    revealed = await browser.post(f"/world/treasures/{treasure_id}/reveal")
    again = await browser.post(f"/world/treasures/{treasure_id}/reveal")
    after = (await browser.get("/world")).json()

    assert (early.status_code, early.json()["error"]) == (409, "TREASURE_NOT_READY")
    assert soon["treasure"] is None
    assert back["treasure"] == {"id": treasure_id}
    assert back["last_visited_at"] is not None
    body = revealed.json()
    assert revealed.status_code == 200
    assert (body["kind"], body["kind_label"]) == ("deeper", "معنى أعمق في الطريق نفسه")
    verse = body["quran"]["verse"]
    assert (verse["surah"], verse["ayah"]) == (6, 99)
    assert hashlib.sha256(verse["text"].encode()).hexdigest() == verse["sha256"]
    assert verse["text"] == next(
        row["text"] for row in EXTRA["verses"] if (row["surah"], row["ayah"]) == (6, 99)
    )
    assert body["hadith"] is None
    assert body["learning_unit"]["id"] == "T01_03"
    assert again.json() == body
    assert after["places"][0]["treasure"] is None
    async with store() as db:
        kinds = (
            await db.scalars(select(EvidenceExposure.kind).order_by(EvidenceExposure.at))
        ).all()
    assert kinds == ["completed", "treasure"]


async def test_an_insight_resting_on_one_text_also_hides_a_treasure(browser, store, flow_settings):
    owner = await as_guest(browser, store, flow_settings)
    no_hadith = {"hadith_collection": None, "hadith_number": None, "hadith_evidence": None}
    no_verse = {"quran_surah": None, "quran_ayah": None, "quran_evidence": None}
    verse_only = await kept(store, owner, **DEEPER, **no_hadith, small_step=None)
    hadith_only = await kept(store, owner, **(DEEPER | no_verse))

    completed = [
        (await browser.post(f"/insights/{insight_id}/complete")).json()
        for insight_id in (verse_only, hadith_only)
    ]

    assert [body["treasure_prepared"] for body in completed] == [True, True]


async def hadith_treasure(store) -> str:
    """Turn the treasure of a completed insight into hadith 2320, ruled صحيح."""
    async with store() as db:
        item = (await db.scalars(select(Treasure))).one()
        item.quran_surah = item.quran_ayah = None
        item.hadith_collection, item.hadith_number = "bukhari", "2320"
        await rule(db, "bukhari", "2320", HadithClassification.SAHIH)
        await db.commit()
        return str(item.id)


@pytest.mark.parametrize("revealed_first", [False, True])
async def test_a_treasure_whose_hadith_was_ruled_out_reveals_nothing(
    browser, store, flow_settings, moving_clock, revealed_first
):
    owner = await as_guest(browser, store, flow_settings)
    await browser.post(f"/insights/{await kept(store, owner, **DEEPER)}/complete")
    treasure_id = await hadith_treasure(store)
    moving_clock.advance(days=4)
    if revealed_first:
        first = await browser.post(f"/world/treasures/{treasure_id}/reveal")
        assert first.json()["hadith"]["hadith"]["number"] == "2320"
    async with store() as db:
        await rule(db, "bukhari", "2320", HadithClassification.DAIF)
        await db.commit()

    world = (await browser.get("/world")).json()
    revealed = await browser.post(f"/world/treasures/{treasure_id}/reveal")

    assert world["places"][0]["treasure"] is None
    assert (revealed.status_code, revealed.json()["error"]) == (404, "NOT_FOUND")
    async with store() as db:
        kinds = (await db.scalars(select(EvidenceExposure.kind))).all()
    assert sorted(kinds) == ["completed", *(["treasure"] if revealed_first else [])]


async def test_a_treasure_also_shows_after_days_or_after_a_related_insight(
    browser, store, flow_settings, moving_clock
):
    owner = await as_guest(browser, store, flow_settings)
    first = await kept(store, owner, **DEEPER)
    await browser.post(f"/insights/{first}/complete")
    assert (await browser.get("/world")).json()["places"][0]["treasure"] is None

    moving_clock.advance(minutes=5)
    related = await kept(store, owner, why={"concept": "الإحياء"}, learning_unit_id="T12_02")
    await browser.post(f"/insights/{related}/complete")
    by_concept = (await browser.get("/world")).json()

    moving_clock.advance(days=3)
    later = (await browser.get("/world")).json()

    flags = [place["treasure"] for place in by_concept["places"]]
    assert flags.count(None) == 1
    # The first by its concept; after three days, the second too.
    assert [place["treasure"] for place in later["places"]].count(None) == 0


async def test_only_the_owner_visits_or_reveals(browser, other, store, flow_settings):
    owner = await as_guest(browser, store, flow_settings)
    insight_id = await kept(store, owner, **DEEPER)
    await browser.post(f"/insights/{insight_id}/complete")
    place_id = (await browser.get("/world")).json()["places"][0]["id"]
    async with store() as db:
        from src.models import Treasure

        treasure_id = (await db.scalars(select(Treasure.id))).one()
    await make_account(store)
    await sign_in(other)

    for path in (
        f"/world/places/{place_id}/visit",
        f"/world/treasures/{treasure_id}/reveal",
        f"/world/places/{7_314_159_265_358_979_323}/visit",
    ):
        response = await other.post(path)
        assert (response.status_code, response.json()["error"]) == (404, "NOT_FOUND")
    assert (await other.get("/world")).json()["places"] == []
    browser.cookies.clear()
    for path in (f"/world/places/{place_id}/visit", f"/world/treasures/{treasure_id}/reveal"):
        assert (await browser.post(path)).status_code == 404


async def test_with_memory_off_a_revealed_treasure_is_not_recorded(browser, store, moving_clock):
    user = await make_account(store)
    await sign_in(browser)
    insight_id = await kept(store, Owner(user_id=user.id), **DEEPER)
    await browser.post(f"/insights/{insight_id}/complete")
    async with store() as db:
        from src.models import Treasure

        treasure_id = (await db.scalars(select(Treasure.id))).one()
        profile = await db.get(Profile, user.id)
        profile.memory_enabled = False
        await db.commit()
    moving_clock.advance(days=4)

    response = await browser.post(f"/world/treasures/{treasure_id}/reveal")

    assert response.status_code == 200
    async with store() as db:
        assert (await db.scalars(select(EvidenceExposure.kind))).all() == ["completed"]


async def test_the_world_and_its_treasures_can_be_switched_off(
    browser, store, flow_settings, flow_app, make_settings, moving_clock
):
    owner = await as_guest(browser, store, flow_settings)
    insight_id = await kept(store, owner, **DEEPER)
    await browser.post(f"/insights/{insight_id}/complete")
    moving_clock.advance(days=4)

    flow_app.state.settings = make_settings(disabled_features="treasure")
    no_treasure = (await browser.get("/world")).json()
    reveal = await browser.post(f"/world/treasures/{7_314_159_265_358_979_323}/reveal")
    flow_app.state.settings = make_settings(disabled_features="world")
    no_world = await browser.get("/world")

    assert no_treasure["places"][0]["treasure"] is None
    assert (reveal.status_code, reveal.json()["error"]) == (404, "FEATURE_DISABLED")
    assert (no_world.status_code, no_world.json()["error"]) == (404, "FEATURE_DISABLED")


async def test_a_place_of_a_region_a_later_map_dropped_keeps_its_id_as_name(
    browser, store, flow_settings
):
    owner = await as_guest(browser, store, flow_settings)
    async with store() as db:
        db.add(WorldPlace(**owner.columns(), region_id="T99", regions_version="0.9"))
        await db.commit()

    body = (await browser.get("/world")).json()

    assert body["places"][0]["name"] == "T99"
    assert load_regions().name_of("T01") == "واحة الغيث"
