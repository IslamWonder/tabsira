"""«تمّ»: saved once, a place in the world, recorded threads, a hidden treasure when one is verified."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.messages import messages_for
from src.models import (
    EvidenceExposure,
    Insight,
    LearnerUnitState,
    Profile,
    RelationReason,
    Treasure,
    TreasureKind,
    WorldPlace,
    WorldRelation,
)
from src.owner import Owner
from src.services import completion_service
from tests.scans.builders import insight_row, scan_row
from tests.scans.conftest import as_guest, make_account, rule, sign_in


async def insights(store, owner: Owner, *units: dict, same_scan: bool = True) -> list[str]:
    async with store() as db:
        scan = scan_row(owner, status="done")
        db.add(scan)
        await db.flush()
        ids = []
        for values in units:
            if not same_scan:
                scan = scan_row(owner, status="done")
                db.add(scan)
                await db.flush()
            row = insight_row(owner, scan_id=scan.id, **values)
            db.add(row)
            await db.flush()
            ids.append(str(row.id))
        await db.commit()
        return ids


async def complete(client, insight_id: str) -> dict:
    response = await client.post(f"/insights/{insight_id}/complete")
    assert response.status_code == 200, response.text
    return response.json()


async def test_the_first_tamm_saves_once_lifts_the_fog_and_suggests_an_account(
    browser, store, flow_settings
):
    owner = await as_guest(browser, store, flow_settings)
    rain, garden = await insights(
        store,
        owner,
        {},
        {"learning_unit_id": "T12_02", "quran_surah": 6, "quran_ayah": 99, "hadith_number": "2320"},
    )

    first = await complete(browser, rain)
    again = await complete(browser, rain)
    second = await complete(browser, garden)

    assert first["first_time"] is True
    assert first["place"]["region_id"] == "T01"
    assert first["place"]["name"] == "واحة الغيث"
    assert first["place"]["created"] is True
    assert first["treasure_prepared"] is False
    assert "first-place" in first["badges_earned"]
    assert [option["id"] for option in first["options"]] == ["open_world", "new_scan", "share"]
    assert first["options"][0]["label"] == messages_for().option_open_world
    assert first["suggest_account"] == messages_for().suggest_account
    assert first["disclosure"] == messages_for().ai_disclosure
    assert (again["first_time"], again["completed_at"]) == (False, first["completed_at"])
    assert (again["place"]["id"], again["place"]["created"]) == (first["place"]["id"], False)
    assert (again["badges_earned"], again["suggest_account"]) == ([], None)
    assert (second["place"]["name"], second["suggest_account"]) == ("بستان النفع", None)
    async with store() as db:
        states = {
            row.unit_id: row.completed_count
            for row in (await db.scalars(select(LearnerUnitState))).all()
        }
        exposures = (await db.scalars(select(EvidenceExposure).order_by(EvidenceExposure.at))).all()
        relations = (await db.scalars(select(WorldRelation))).all()
        places = (await db.scalars(select(WorldPlace))).all()
    assert states == {"T01_06": 1, "T12_02": 1}
    assert [(e.quran_surah, e.quran_ayah, e.hadith_number, e.concept) for e in exposures] == [
        (30, 50, None, "الإحياء"),
        (6, 99, None, "الإحياء"),
    ]
    assert [relation.reason for relation in relations] == [RelationReason.SAME_SCENE]
    assert {place.region_id for place in places} == {"T01", "T12"}


async def test_a_verified_treasure_is_hidden_when_a_deeper_unit_has_one(
    browser, store, flow_settings
):
    owner = await as_guest(browser, store, flow_settings)
    async with store() as db:
        await rule(db, "bukhari", "1032")
        await db.commit()
    (insight_id,) = await insights(
        store, owner, {"learning_unit_id": "T01_01", "quran_surah": 3, "quran_ayah": 190}
    )

    first = await complete(browser, insight_id)
    again = await complete(browser, insight_id)

    assert first["treasure_prepared"] is True
    assert again["treasure_prepared"] is True
    async with store() as db:
        treasure = (await db.scalars(select(Treasure))).one()
        exposure = (await db.scalars(select(EvidenceExposure))).one()
    assert (
        treasure.kind,
        treasure.quran_surah,
        treasure.quran_ayah,
        treasure.learning_unit_id,
    ) == (
        TreasureKind.DEEPER,
        6,
        99,
        "T01_03",
    )
    assert treasure.revealed_at is None
    assert (exposure.hadith_collection, exposure.hadith_number) == ("bukhari", "1032")


async def test_threads_join_places_whose_units_the_path_links(browser, store, flow_settings):
    owner = await as_guest(browser, store, flow_settings)
    first, second, third = await insights(
        store,
        owner,
        {"learning_unit_id": "T02_01", "quran_surah": 2, "quran_ayah": 1},
        {"learning_unit_id": "T01_01", "quran_surah": 3, "quran_ayah": 190},
        {"learning_unit_id": None, "learning_path_version": None},
        same_scan=False,
    )

    await complete(browser, first)
    await complete(browser, second)
    gate = await complete(browser, third)

    assert gate["place"]["region_id"] == "T00"
    async with store() as db:
        relations = (await db.scalars(select(WorldRelation))).all()
    assert [relation.reason for relation in relations] == [RelationReason.PREREQUISITE]


async def test_with_memory_off_the_place_is_kept_but_no_learning_is_recorded(
    browser, store, flow_settings
):
    user = await make_account(store)
    await sign_in(browser)
    async with store() as db:
        profile = await db.get(Profile, user.id)
        profile.memory_enabled = False
        await db.commit()
    (insight_id,) = await insights(store, Owner(user_id=user.id), {})

    body = await complete(browser, insight_id)

    assert body["place"]["region_id"] == "T01"
    assert body["suggest_account"] is None
    async with store() as db:
        assert (await db.scalars(select(LearnerUnitState))).all() == []
        assert (await db.scalars(select(EvidenceExposure))).all() == []


async def test_the_world_and_the_treasure_can_be_switched_off(
    browser, store, flow_settings, flow_app, make_settings
):
    owner = await as_guest(browser, store, flow_settings)
    plain, unit = await insights(
        store, owner, {}, {"learning_unit_id": "T01_01", "quran_surah": 3, "quran_ayah": 190}
    )

    flow_app.state.settings = make_settings(feature_world=False)
    without_world = await complete(browser, plain)
    flow_app.state.settings = make_settings(feature_treasure=False)
    without_treasure = await complete(browser, unit)

    assert without_world["place"] is None
    assert (without_treasure["place"]["region_id"], without_treasure["treasure_prepared"]) == (
        "T01",
        False,
    )
    async with store() as db:
        assert (await db.get(Insight, int(plain))).completed_at is not None
        assert (await db.scalars(select(Treasure))).all() == []


async def test_a_save_that_fails_says_so(browser, store, flow_settings, monkeypatch):
    owner = await as_guest(browser, store, flow_settings)
    (insight_id,) = await insights(store, owner, {})

    async def broken(*_args, **_kwargs):
        message = "connection lost"
        raise SQLAlchemyError(message)

    monkeypatch.setattr(completion_service, "complete", broken)
    response = await browser.post(f"/insights/{insight_id}/complete")

    assert (response.status_code, response.json()["error"]) == (503, "SAVE_FAILED")
