"""Guests: the signed cookie, expiry, and the merge into an account at sign-in."""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Response
from sqlalchemy import select
from starlette.requests import Request

from src import clock
from src.models import (
    EvidenceExposure,
    Guest,
    Insight,
    InsightOrigin,
    LearnerUnitState,
    RelationReason,
    Scan,
    ScanSource,
    ScanStatus,
    Treasure,
    TreasureKind,
    WorldPlace,
    WorldRelation,
)
from src.owner import Owner, optional_owner, owner_for_write
from src.redis_client import close_redis, get_redis
from src.services import guest_service
from tests.scans.conftest import make_account

PATH = "tabsira-masar-1.0"


def request_with(cookies: dict[str, str]) -> Request:
    header = "; ".join(f"{name}={value}" for name, value in cookies.items())
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"cookie", header.encode())] if header else [],
            "app": FastAPI(),
        }
    )


def test_a_guest_cookie_is_signed_and_only_its_hash_is_stored(flow_settings):
    token = "t" * 43
    value = guest_service.cookie_value(flow_settings, token)
    name = flow_settings.guest_cookie_name

    assert guest_service.cookie_token(request_with({name: value}), flow_settings) == token
    assert guest_service.key_of(token) != token
    assert len(guest_service.key_of(token)) == 64
    forged = value[:-1] + ("0" if value[-1] != "0" else "1")
    for refused in ({}, {name: forged}, {name: "x" * 200}, {name: f".{value.split('.')[1]}"}):
        assert guest_service.cookie_token(request_with(refused), flow_settings) is None


def test_the_guest_cookie_is_httponly_secure_and_lax(flow_settings):
    response = Response()
    guest_service.set_cookie(response, flow_settings, "token")
    guest_service.clear_cookie(response, flow_settings)

    first, cleared = response.headers.getlist("set-cookie")
    assert first.startswith("__Secure-tabsira_guest=token.")
    for part in ("HttpOnly", "Secure", "SameSite=lax", "Domain=.tabsira.test", "Max-Age=7776000"):
        assert part in first
    assert "Max-Age=0" in cleared


async def test_a_guest_lives_while_it_is_seen_and_expires_with_what_it_saved(
    store, flow_settings, moving_clock
):
    async with store() as db:
        token, guest = await guest_service.create(db, flow_settings)
        db.add(LearnerUnitState(guest_key=guest.key, path_version=PATH, unit_id="T01_06"))
        db.add(EvidenceExposure(guest_key=guest.key, kind="completed", quran_surah=30))
        await db.commit()

        moving_clock.advance(hours=2)
        found = await guest_service.find(db, flow_settings, token)
        assert found is not None
        assert found.last_seen_at == moving_clock.now
        moving_clock.advance(minutes=10)
        assert (await guest_service.find(db, flow_settings, token)).last_seen_at < moving_clock.now
        assert await guest_service.find(db, flow_settings, "unknown") is None

        moving_clock.advance(days=91)
        assert await guest_service.find(db, flow_settings, token) is None
        _new_token, newcomer = await guest_service.create(db, flow_settings)
        await db.commit()

        assert [row.key for row in (await db.scalars(select(Guest))).all()] == [newcomer.key]
        assert (await db.scalars(select(LearnerUnitState))).all() == []
        assert (await db.scalars(select(EvidenceExposure))).all() == []


async def test_owners_filter_and_own_their_rows():
    user, guest = Owner(user_id=uuid.uuid4()), Owner(guest_key="g" * 64)

    assert not user.is_guest
    assert guest.is_guest
    assert user.columns() == {"user_id": user.user_id, "guest_key": None}
    assert "user_id" in str(user.where(Scan))
    assert "guest_key" in str(guest.where(Scan))
    assert user.owns(Scan(user_id=user.user_id))
    assert not user.owns(Scan(guest_key="g" * 64))
    assert guest.owns(Scan(guest_key="g" * 64))
    assert not guest.owns(Scan(user_id=user.user_id))


async def test_the_owner_of_a_request(maker, flow_settings):
    async with maker() as db:
        token, guest = await guest_service.create(db, flow_settings)
        await db.commit()
        name = flow_settings.guest_cookie_name
        signed = guest_service.cookie_value(flow_settings, token)
        user = await make_account(maker)

        assert await optional_owner(request_with({}), db, flow_settings, None) is None
        assert (
            await optional_owner(
                request_with({name: guest_service.cookie_value(flow_settings, "gone")}),
                db,
                flow_settings,
                None,
            )
            is None
        )
        assert await optional_owner(request_with({name: signed}), db, flow_settings, None) == (
            Owner(guest_key=guest.key)
        )
        assert await optional_owner(request_with({name: signed}), db, flow_settings, user) == (
            Owner(user_id=user.id)
        )

        response = Response()
        kept = await owner_for_write(response, db, flow_settings, Owner(guest_key=guest.key))
        assert kept == Owner(guest_key=guest.key)
        assert "set-cookie" not in response.headers
        made = await owner_for_write(response, db, flow_settings, None)
        assert made.guest_key is not None
        assert made.guest_key != guest.key
        assert response.headers["set-cookie"].startswith(name)


async def test_merging_a_guest_moves_everything_it_saved_to_the_account(store, flow_settings):
    user = await make_account(store)
    async with store() as db:
        _token, guest = await guest_service.create(db, flow_settings)
        key = guest.key
        scan = Scan(
            guest_key=key, source=ScanSource.UPLOAD, status=ScanStatus.DONE, engine="pipeline"
        )
        db.add(scan)
        await db.flush()

        def insight(**values):
            return Insight(
                **values,
                engine="pipeline",
                title="t",
                glimpse="g",
                relation="direct",
                explanation=[],
                why={"concept": "c"},
            )

        guest_rain = WorldPlace(guest_key=key, region_id="T01", regions_version="1.0")
        guest_garden = WorldPlace(guest_key=key, region_id="T12", regions_version="1.0")
        guest_gate = WorldPlace(guest_key=key, region_id="T00", regions_version="1.0")
        kept_rain = WorldPlace(user_id=user.id, region_id="T01", regions_version="1.0")
        kept_garden = WorldPlace(user_id=user.id, region_id="T12", regions_version="1.0")
        db.add_all([guest_rain, guest_garden, guest_gate, kept_rain, kept_garden])
        await db.flush()
        guest_rain.last_visited_at = clock.utcnow()
        first = insight(guest_key=key, origin=InsightOrigin.SCAN, scan_id=scan.id)
        second = insight(guest_key=key, origin=InsightOrigin.SCAN, scan_id=scan.id)
        theirs = insight(user_id=user.id, origin=InsightOrigin.TUTORIAL, tutorial_slug="drop")
        db.add_all([first, second, theirs])
        await db.flush()
        first.place_id, second.place_id = guest_rain.id, guest_garden.id
        db.add(
            Treasure(
                insight_id=first.id,
                place_id=guest_rain.id,
                kind=TreasureKind.ALTERNATIVE,
                quran_surah=6,
                quran_ayah=99,
                learning_unit_id="T01_03",
                learning_path_version=PATH,
            )
        )
        for low, high in (
            sorted([guest_rain.id, guest_garden.id]),
            sorted([guest_rain.id, guest_gate.id]),
            sorted([kept_rain.id, kept_garden.id]),
        ):
            db.add(
                WorldRelation(
                    place_a_id=low,
                    place_b_id=high,
                    reason=RelationReason.SAME_SCENE,
                    insight_a_id=first.id,
                    insight_b_id=second.id,
                )
            )
        db.add_all(
            [
                LearnerUnitState(
                    guest_key=key, path_version=PATH, unit_id="T01_06", completed_count=2
                ),
                LearnerUnitState(
                    guest_key=key, path_version=PATH, unit_id="T12_02", completed_count=1
                ),
                LearnerUnitState(
                    user_id=user.id, path_version=PATH, unit_id="T01_06", completed_count=1
                ),
                EvidenceExposure(guest_key=key, kind="completed", quran_surah=30, quran_ayah=50),
            ]
        )
        await db.commit()

        assert await guest_service.merge_into_user(db, key, user.id)
        await db.commit()
        assert not await guest_service.merge_into_user(db, key, user.id)

        assert await db.get(Guest, key) is None
        assert (await db.scalars(select(Scan.user_id))).all() == [user.id]
        assert set((await db.scalars(select(Insight.user_id))).all()) == {user.id}
        places = {place.region_id: place for place in (await db.scalars(select(WorldPlace))).all()}
        assert set(places) == {"T00", "T01", "T12"}
        assert {place.user_id for place in places.values()} == {user.id}
        assert places["T01"].id == kept_rain.id
        assert places["T01"].last_visited_at is not None
        assert (await db.scalars(select(Insight.place_id).where(Insight.id == first.id))).one() == (
            kept_rain.id
        )
        assert (await db.scalars(select(Treasure.place_id))).one() == kept_rain.id
        threads = {
            frozenset((relation.place_a_id, relation.place_b_id))
            for relation in (await db.scalars(select(WorldRelation))).all()
        }
        assert threads == {
            frozenset((kept_rain.id, kept_garden.id)),
            frozenset((kept_rain.id, guest_gate.id)),
        }
        states = {
            row.unit_id: row.completed_count
            for row in (await db.scalars(select(LearnerUnitState))).all()
        }
        assert states == {"T01_06": 3, "T12_02": 1}
        assert (await db.scalars(select(EvidenceExposure.user_id))).all() == [user.id]


async def test_the_redis_client_is_shared_by_the_process_and_closed_with_it(flow_settings):
    client = get_redis(flow_settings)

    assert get_redis(flow_settings) is client
    await close_redis()
    assert get_redis(flow_settings) is not client
    await close_redis()
