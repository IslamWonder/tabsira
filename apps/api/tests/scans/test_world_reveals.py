"""The world picture (decision 59): one reveal per learned concept, in a fixed slot, made with «تمّ»."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import select, update

from src import clock
from src.models import Guest, Insight, WorldPlace, WorldReveal
from src.owner import Owner
from src.services import guest_service, world_service
from src.services.content import LAYOUT_PATH, Layout, load_layout
from tests.scans.builders import insight_row, scan_row
from tests.scans.conftest import as_guest, make_account, sign_in


async def kept(store, owner: Owner, **values) -> str:
    """Keep an insight of a done scan for `owner`; return its id."""
    async with store() as db:
        scan = scan_row(owner, status="done")
        db.add(scan)
        await db.flush()
        row = insight_row(owner, scan_id=scan.id, **values)
        db.add(row)
        await db.commit()
        return str(row.id)


def slot(region_id: str, index: int) -> tuple[float, float, float]:
    found = load_layout().region(region_id)
    assert found is not None
    circle = found.slots[index]
    return circle.x, circle.y, circle.radius


def circle(reveal: dict) -> tuple[float, float, float]:
    return reveal["x"], reveal["y"], reveal["radius"]


async def test_a_first_completion_reveals_its_region_landmark_once(browser, store, flow_settings):
    owner = await as_guest(browser, store, flow_settings)
    insight_id = await kept(store, owner)

    first = (await browser.post(f"/insights/{insight_id}/complete")).json()
    again = (await browser.post(f"/insights/{insight_id}/complete")).json()
    world = (await browser.get("/world")).json()

    assert first["reveal"]["landmark"] is True
    assert first["reveal"]["created"] is True
    assert again["reveal"] == {**first["reveal"], "created": False}
    assert world["layout_version"] == "1"
    (reveal,) = world["reveals"]
    assert reveal["id"] == first["reveal"]["id"]
    assert (reveal["region_id"], reveal["theme"], reveal["icon"]) == ("T01", "water", "drop")
    assert circle(reveal) == slot("T01", 0)
    assert reveal["insight_id"] == insight_id
    assert reveal["place_id"] == world["places"][0]["id"]
    assert reveal["landmark"] is True
    assert reveal["shown"] is False
    assert world["places"][0]["insights"][0]["reveal_id"] == reveal["id"]
    async with store() as db:
        row = (await db.scalars(select(WorldReveal))).one()
        insight = await db.get(Insight, int(insight_id))
        assert insight is not None
        assert row.learned_at == insight.completed_at
        assert row.concept_key == "unit:T01_06"


async def test_learning_a_concept_again_widens_nothing(browser, store, flow_settings):
    owner = await as_guest(browser, store, flow_settings)
    first = await kept(store, owner)
    second = await kept(store, owner, title="الماء والحياة")

    made = (await browser.post(f"/insights/{first}/complete")).json()
    repeated = (await browser.post(f"/insights/{second}/complete")).json()
    world = (await browser.get("/world")).json()

    assert repeated["first_time"] is True
    assert repeated["reveal"] == {**made["reveal"], "created": False}
    assert len(world["reveals"]) == 1
    listed = world["places"][0]["insights"]
    assert [item["title"] for item in listed] == ["الحياة في قطرة", "الماء والحياة"]
    assert {item["reveal_id"] for item in listed} == {made["reveal"]["id"]}


async def test_another_concept_of_a_region_takes_its_next_slot(browser, store, flow_settings):
    owner = await as_guest(browser, store, flow_settings)
    rain = await kept(store, owner)
    growth = await kept(store, owner, learning_unit_id="T01_03")
    garden = await kept(store, owner, learning_unit_id="T12_02")

    for insight_id in (rain, growth, garden):
        await browser.post(f"/insights/{insight_id}/complete")
    reveals = (await browser.get("/world")).json()["reveals"]

    assert [(item["region_id"], item["landmark"]) for item in reveals] == [
        ("T01", True),
        ("T01", False),
        ("T12", True),
    ]
    assert circle(reveals[1]) == slot("T01", 1)
    assert circle(reveals[2]) == slot("T12", 0)
    assert reveals[2]["theme"] == "planting"


async def test_a_full_region_widens_no_more_and_keeps_every_insight(
    browser, store, flow_settings, monkeypatch
):
    owner = await as_guest(browser, store, flow_settings)
    capacity = len(load_layout().region("T00").slots)  # type: ignore[union-attr]
    # Insights with no unit: each its own concept, all in the fallback region.
    ids = [
        await kept(store, owner, learning_unit_id=None, title=f"بصيرة {index}")
        for index in range(capacity + 1)
    ]

    answers = [(await browser.post(f"/insights/{item}/complete")).json() for item in ids]
    world = (await browser.get("/world")).json()

    assert [answer["reveal"] is not None for answer in answers] == [True] * capacity + [False]
    assert len(world["reveals"]) == capacity
    assert {item["region_id"] for item in world["reveals"]} == {"T00"}
    (place,) = world["places"]
    assert len(place["insights"]) == capacity + 1
    assert place["insights"][-1]["reveal_id"] is None
    # The insight without room is passed over by every later load, without a query.
    tries: list[str] = []

    async def counted(*args: Any) -> Any:
        tries.append(args[2].title)
        return None, False

    monkeypatch.setattr(world_service, "reveal_concept", counted)
    assert len((await browser.get("/world")).json()["reveals"]) == capacity
    assert tries == []


def stale_once(real: Callable[..., Awaitable[Any]], stale: Any) -> Callable[..., Awaitable[Any]]:
    """
    Answer `stale` the first time, then read for real.

    It stands for a completion running at the same moment as another, which commits its
    reveal between this one's read and its write; the test database has one connection,
    so two requests cannot really overlap here.
    """
    calls = 0

    async def read(*args: Any) -> Any:
        nonlocal calls
        calls += 1
        return stale if calls == 1 else await real(*args)

    return read


async def test_a_completion_that_loses_a_slot_takes_the_next(
    browser, store, flow_settings, monkeypatch
):
    owner = await as_guest(browser, store, flow_settings)
    one = await kept(store, owner, learning_unit_id="T01_02")
    two = await kept(store, owner, learning_unit_id="T01_03")
    await browser.post(f"/insights/{one}/complete")
    monkeypatch.setattr(
        world_service, "_taken_slots", stale_once(world_service._taken_slots, set())
    )

    answer = (await browser.post(f"/insights/{two}/complete")).json()

    assert answer["reveal"]["created"] is True
    assert answer["reveal"]["landmark"] is False
    async with store() as db:
        slots = sorted((await db.scalars(select(WorldReveal.slot))).all())
    assert slots == [0, 1]


async def test_a_concept_revealed_meanwhile_is_not_revealed_twice(
    browser, store, flow_settings, monkeypatch
):
    owner = await as_guest(browser, store, flow_settings)
    one = await kept(store, owner)
    two = await kept(store, owner)
    made = (await browser.post(f"/insights/{one}/complete")).json()["reveal"]
    monkeypatch.setattr(world_service, "_reveal_of", stale_once(world_service._reveal_of, None))

    answer = (await browser.post(f"/insights/{two}/complete")).json()

    assert answer["reveal"] == {**made, "created": False}
    async with store() as db:
        assert len((await db.scalars(select(WorldReveal))).all()) == 1


async def test_what_was_learned_before_reveals_is_revealed_without_the_effect(
    browser, store, flow_settings, flow_app, make_settings
):
    owner = await as_guest(browser, store, flow_settings)
    rain = await kept(store, owner)
    flow_app.state.settings = make_settings(disabled_features="world")
    without_world = (await browser.post(f"/insights/{rain}/complete")).json()
    flow_app.state.settings = flow_settings
    # A completion recorded before reveals existed: a place, no reveal.
    garden = await kept(store, owner, learning_unit_id="T12_02")
    async with store() as db:
        place = WorldPlace(**owner.columns(), region_id="T12", regions_version="1.0")
        db.add(place)
        await db.flush()
        await db.execute(
            update(Insight)
            .where(Insight.id == int(garden))
            .values(completed_at=clock.utcnow(), place_id=place.id)
        )
        await db.commit()

    world = (await browser.get("/world")).json()
    again = (await browser.get("/world")).json()

    assert (without_world["place"], without_world["reveal"]) == (None, None)
    assert [(item["region_id"], item["shown"]) for item in world["reveals"]] == [
        ("T01", True),
        ("T12", True),
    ]
    assert again["reveals"] == world["reveals"]
    assert {place["region_id"] for place in world["places"]} == {"T01", "T12"}
    async with store() as db:
        insight = await db.get(Insight, int(rain))
        assert insight is not None
        assert insight.place_id is not None


async def test_a_reveal_is_marked_shown_by_its_owner_only(browser, other, store, flow_settings):
    owner = await as_guest(browser, store, flow_settings)
    insight_id = await kept(store, owner)
    reveal_id = (await browser.post(f"/insights/{insight_id}/complete")).json()["reveal"]["id"]
    await make_account(store)
    await sign_in(other)

    stranger = await other.post("/world/reveals/shown", json={"ids": [reveal_id]})
    after_stranger = (await browser.get("/world")).json()["reveals"][0]["shown"]
    mine = await browser.post("/world/reveals/shown", json={"ids": [reveal_id]})
    twice = await browser.post("/world/reveals/shown", json={"ids": [reveal_id]})
    world = (await browser.get("/world")).json()

    assert stranger.status_code == 204
    assert after_stranger is False
    assert (mine.status_code, twice.status_code) == (204, 204)
    assert world["reveals"][0]["shown"] is True
    assert (await other.get("/world")).json()["reveals"] == []
    assert (await browser.post("/world/reveals/shown", json={"ids": []})).status_code == 422
    browser.cookies.clear()
    assert (await browser.post("/world/reveals/shown", json={"ids": [reveal_id]})).status_code == (
        204
    )


async def test_a_signed_in_account_gets_its_own_reveals(browser, store):
    user = await make_account(store)
    await sign_in(browser)
    insight_id = await kept(store, Owner(user_id=user.id), learning_unit_id="T13_01")

    answer = (await browser.post(f"/insights/{insight_id}/complete")).json()
    reveal = (await browser.get("/world")).json()["reveals"][0]

    assert answer["reveal"]["created"] is True
    assert (reveal["region_id"], reveal["theme"], reveal["icon"]) == ("T13", "patience", "path")
    export = (await browser.get("/account/export")).json()
    (exported,) = export["learning"]["reveals"]
    assert (exported["concept_key"], exported["slot"]) == ("unit:T13_01", 0)


async def test_merging_a_guest_moves_the_reveals_the_account_has_room_for(store, flow_settings):
    user = await make_account(store)
    account = Owner(user_id=user.id)
    async with store() as db:
        _token, guest = await guest_service.create(db, flow_settings)
        visitor = Owner(guest_key=guest.key)

        async def learned(owner: Owner, unit: str) -> Insight:
            scan = scan_row(owner, status="done")
            db.add(scan)
            await db.flush()
            row = insight_row(owner, scan_id=scan.id, learning_unit_id=unit)
            row.completed_at = clock.utcnow()
            db.add(row)
            await db.flush()
            place = await world_service._place_of(db, owner, row)
            await world_service.reveal_concept(db, owner, row, place)
            return row

        await learned(account, "T01_06")
        await learned(visitor, "T01_06")  # a concept the account has: dropped
        await learned(visitor, "T01_02")  # slot 1 of T01 in the guest's world, free: moved
        await learned(visitor, "T12_02")  # a region the account has not opened: moved
        await db.commit()

        assert await guest_service.merge_into_user(db, flow_settings, guest.key, user.id)
        await db.commit()

        assert await db.get(Guest, guest.key) is None
        rows = (await db.scalars(select(WorldReveal).order_by(WorldReveal.learned_at))).all()
        assert [(row.concept_key, row.slot) for row in rows] == [
            ("unit:T01_06", 0),
            ("unit:T01_02", 1),
            ("unit:T12_02", 0),
        ]
        assert {row.user_id for row in rows} == {user.id}
        places = {place.id: place for place in (await db.scalars(select(WorldPlace))).all()}
        assert {places[row.place_id].region_id for row in rows} == {"T01", "T12"}
        assert all(places[row.place_id].user_id == user.id for row in rows)


async def test_a_merge_that_drops_a_reveal_lets_the_world_reveal_it_again(
    browser, store, flow_settings
):
    user = await make_account(store)
    account = Owner(user_id=user.id)
    async with store() as db:
        _token, guest = await guest_service.create(db, flow_settings)
        visitor = Owner(guest_key=guest.key)
        rows = []
        for owner, unit in ((account, "T01_02"), (visitor, "T01_03")):
            scan = scan_row(owner, status="done")
            db.add(scan)
            await db.flush()
            row = insight_row(owner, scan_id=scan.id, learning_unit_id=unit)
            row.completed_at = clock.utcnow()
            db.add(row)
            await db.flush()
            place = await world_service._place_of(db, owner, row)
            await world_service.reveal_concept(db, owner, row, place)
            rows.append(row)
        await db.commit()
        # Both took slot 0 of T01: the guest's goes, its insight stays.
        assert await guest_service.merge_into_user(db, flow_settings, guest.key, user.id)
        await db.commit()
    await sign_in(browser)

    reveals = (await browser.get("/world")).json()["reveals"]

    assert [(item["insight_id"], item["landmark"], item["shown"]) for item in reveals] == [
        (str(rows[0].id), True, False),
        (str(rows[1].id), False, True),
    ]


async def test_a_completion_gives_up_rather_than_race_for_ever(
    browser, store, flow_settings, monkeypatch
):
    owner = await as_guest(browser, store, flow_settings)
    one = await kept(store, owner)
    two = await kept(store, owner)
    await browser.post(f"/insights/{one}/complete")

    async def nothing(*_args: Any) -> Any:
        return None

    async def no_slot(*_args: Any) -> set[int]:
        return set()

    monkeypatch.setattr(world_service, "_reveal_of", nothing)
    monkeypatch.setattr(world_service, "_taken_slots", no_slot)

    answer = await browser.post(f"/insights/{two}/complete")

    assert answer.status_code == 200
    assert answer.json()["reveal"] is None


async def test_a_region_the_layout_does_not_place_is_revealed_nowhere(
    browser, store, flow_settings
):
    owner = await as_guest(browser, store, flow_settings)
    insight_id = await kept(store, owner)
    async with store() as db:
        place = WorldPlace(**owner.columns(), region_id="T99", regions_version="0.9")
        db.add(place)
        await db.flush()
        await db.execute(
            update(Insight)
            .where(Insight.id == int(insight_id))
            .values(completed_at=clock.utcnow(), place_id=place.id)
        )
        await db.commit()
    first = (await browser.get("/world")).json()
    async with store() as db:
        db.add(
            WorldReveal(
                **owner.columns(),
                insight_id=int(insight_id),
                place_id=place.id,
                concept_key="unit:T99_01",
                region_id="T99",
                layout_version="0",
                slot=0,
                theme="water",
                x=0.5,
                y=0.5,
                radius=0.1,
                learned_at=clock.utcnow(),
            )
        )
        await db.commit()

    later = (await browser.get("/world")).json()

    assert first["reveals"] == []
    assert first["places"][0]["insights"][0]["reveal_id"] is None
    assert [(item["region_id"], item["icon"]) for item in later["reveals"]] == [("T99", "")]


# Reveals keep the circle a released layout gave them: the file never changes once released.
LAYOUT_1_SHA256 = "77526e11814098ad57f401a12dae452ddc28e094e0290047527ed7031d29dcde"


def test_the_released_layout_lays_out_every_region_and_never_changes():
    layout = load_layout()

    assert hashlib.sha256(LAYOUT_PATH.read_bytes()).hexdigest() == LAYOUT_1_SHA256
    assert (layout.version, layout.regions_version) == ("1", "1.0")
    assert {region.id for region in layout.regions} == {f"T{n:02d}" for n in range(16)}
    # One slot per unit of the region's domain (masar: six each).
    assert {len(region.slots) for region in layout.regions} == {6}


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda d: d["regions"].append(dict(d["regions"][0])), "laid out twice"),
        (lambda d: d["regions"][0]["slots"].append([0.5, 0.5, 0.3]), "less than or equal"),
        (lambda d: d["regions"][0]["slots"].append([1.2, 0.5, 0.1]), "less than or equal"),
        (lambda d: d["regions"][0]["slots"].append([0.5, 0.5]), "zip"),
        (lambda d: d["regions"][0].__setitem__("theme", "fire"), "theme"),
        (lambda d: d["regions"][0].__setitem__("slots", []), "at least 1"),
        (lambda d: d["regions"][0].__setitem__("slots", "none"), "valid list"),
    ],
)
def test_a_broken_layout_is_refused(change, reason):
    data = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
    change(data)

    with pytest.raises(ValidationError, match=reason):
        Layout.model_validate(data)


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.__setitem__("regions", d["regions"][1:]),
        lambda d: d.__setitem__("regions_version", "0.9"),
    ],
)
def test_a_layout_that_misses_the_regions_file_is_refused(change, tmp_path):
    data = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
    change(data)
    path = tmp_path / "layout.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="does not lay out"):
        load_layout(path)


async def test_a_place_the_layout_does_not_place_gets_no_reveal(store, flow_settings):
    async with store() as db:
        _token, guest = await guest_service.create(db, flow_settings)
        owner = Owner(guest_key=guest.key)
        place = WorldPlace(**owner.columns(), region_id="T99", regions_version="0.9")
        scan = scan_row(owner, status="done")
        db.add_all([place, scan])
        await db.flush()
        row = insight_row(owner, scan_id=scan.id, place_id=place.id, completed_at=clock.utcnow())
        db.add(row)
        await db.flush()

        assert await world_service.reveal_concept(db, owner, row, place) == (None, False)


async def test_an_expired_guest_goes_with_its_reveals(browser, store, flow_settings):
    owner = await as_guest(browser, store, flow_settings)
    await browser.post(f"/insights/{await kept(store, owner)}/complete")
    async with store() as db:
        await db.execute(
            update(Guest)
            .where(Guest.key == owner.guest_key)
            .values(last_seen_at=clock.utcnow() - timedelta(days=flow_settings.guest_ttl_days + 1))
        )
        await db.commit()
        assert len((await db.scalars(select(WorldReveal))).all()) == 1

        assert await guest_service.purge_expired(db, flow_settings) == 1
        await db.commit()

        assert (await db.scalars(select(WorldReveal))).all() == []


async def learned_long_ago(
    store, owner: Owner, insight_ids: list[str], place_id: int | None = None
):
    """Mark insights completed with no reveal made, as before reveals existed."""
    async with store() as db:
        await db.execute(
            update(Insight)
            .where(Insight.id.in_([int(one) for one in insight_ids]))
            .values(completed_at=clock.utcnow(), place_id=place_id)
        )
        await db.commit()


async def test_two_old_insights_of_one_concept_reveal_it_once(browser, store, flow_settings):
    owner = await as_guest(browser, store, flow_settings)
    first = await kept(store, owner)
    second = await kept(store, owner)
    await learned_long_ago(store, owner, [first, second])

    world = (await browser.get("/world")).json()

    assert [item["region_id"] for item in world["reveals"]] == ["T01"]
    async with store() as db:
        assert len((await db.scalars(select(WorldReveal))).all()) == 1


async def test_an_old_insight_whose_place_was_made_meanwhile_uses_that_place(
    browser, store, flow_settings, monkeypatch
):
    owner = await as_guest(browser, store, flow_settings)
    old = await kept(store, owner)
    async with store() as db:
        place = WorldPlace(**owner.columns(), region_id="T01", regions_version="1.0")
        db.add(place)
        await db.commit()
        place_id = place.id
    await learned_long_ago(store, owner, [old], place_id)

    # The place is made by another request after this one listed the owner's places.
    async def no_places(db, owner):
        return []

    monkeypatch.setattr(world_service, "_places", no_places)

    assert await _ensure(store, owner) is True

    async with store() as db:
        reveal = (await db.scalars(select(WorldReveal))).one()
        assert reveal.place_id == place_id


async def _ensure(store, owner: Owner) -> bool:
    async with store() as db:
        made = await world_service.ensure_reveals(db, owner)
        await db.commit()
        return made


async def test_a_concept_revealed_by_another_request_meanwhile_counts_as_not_made(
    browser, store, flow_settings, monkeypatch
):
    owner = await as_guest(browser, store, flow_settings)
    old = await kept(store, owner)
    await learned_long_ago(store, owner, [old])
    real = world_service.reveal_concept

    async def after_a_rival(db, owner, insight, place):
        # Another request commits this concept's reveal between the read and the write.
        db.add(
            WorldReveal(
                **owner.columns(),
                insight_id=insight.id,
                place_id=place.id,
                concept_key=world_service.concept_key(insight),
                region_id=place.region_id,
                layout_version=load_layout().version,
                slot=0,
                theme="water",
                x=0.5,
                y=0.5,
                radius=0.1,
                learned_at=clock.utcnow(),
            )
        )
        await db.flush()
        return await real(db, owner, insight, place)

    monkeypatch.setattr(world_service, "reveal_concept", after_a_rival)

    assert await _ensure(store, owner) is False
