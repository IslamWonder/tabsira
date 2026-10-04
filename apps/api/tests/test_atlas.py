"""
«أطلس بصائر العالم»: placing, publishing and withdrawing, and what the public map may see.

The one rule every test here guards: the exact point an owner gives never reaches a public
answer. Public responses are searched for the owner's coordinates and for any key that could
name a private location.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.geo.privacy import approximate
from src.models import MapCapturePoint, MapEntry
from src.owner import Owner
from src.services import sitemap_service
from src.services.sitemap_service import Section
from tests import geo_dataset as world_data
from tests.geo_dataset import TUNIS, TUNIS_CITY
from tests.scans.builders import insight_row, scan_row
from tests.support_social import Member

# Where the owner says the photo was taken: a point inside Tunis, given to the exact metre.
EXACT = (36.806512, 10.181534)
CELL_M = 1000
PRIVATE_KEYS = {"latitude", "longitude", "capture", "accuracy_m", "captured_at", "measured_at"}


async def _insight(db: AsyncSession, member: Member, **values: Any) -> int:
    owner = Owner(user_id=member.user.id)
    scan = scan_row(owner)
    db.add(scan)
    await db.flush()
    insight = insight_row(owner, scan_id=scan.id, **values)
    db.add(insight)
    await db.flush()
    return insight.id


async def _place(member: Member, insight_id: int, **body: Any) -> Any:
    payload = {
        "latitude": EXACT[0],
        "longitude": EXACT[1],
        "accuracy_m": 12,
        "source": "device_capture",
        **body,
    }
    return await member.http.put(f"/insights/{insight_id}/map", json=payload)


async def _published(member: Member, insight_id: int) -> str:
    assert (await _place(member, insight_id)).status_code == 200
    response = await member.http.post(f"/insights/{insight_id}/map/publish")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "published"
    return str(response.json()["id"])


def keys_of(value: Any) -> set[str]:
    """Every key in a JSON document, however deep."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            found.add(key)
            found |= keys_of(child)
    elif isinstance(value, list):
        for child in value:
            found |= keys_of(child)
    return found


def assert_public(response: Any) -> None:
    """A public answer holds neither the exact point nor any field that could name one."""
    body = response.json()
    assert not (keys_of(body) & PRIVATE_KEYS), keys_of(body) & PRIVATE_KEYS
    assert str(EXACT[0]) not in response.text
    assert str(EXACT[1]) not in response.text


@pytest.fixture
async def world(db_session: AsyncSession, scripture: None) -> None:
    await world_data.load_world(db_session)


# ─── The owner's side ───


async def test_placing_keeps_the_exact_point_private_and_previews_the_cell(
    db_session, make_member, make_insight, world
):
    author = await make_member("author")
    insight_id = await _insight(db_session, author)

    response = await _place(author, insight_id, captured_at="2026-10-04T08:00:00Z")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "draft"
    # The owner gets their own point back, and nobody else does (see the public tests).
    assert (body["capture"]["latitude"], body["capture"]["longitude"]) == EXACT
    assert body["capture"]["source"] == "device_capture"
    centre = approximate(*EXACT, CELL_M)
    assert body["public"]["point"]["coordinates"] == [centre.lng, centre.lat]
    assert body["public"]["cell_m"] == CELL_M
    assert body["public"]["precision_label"] == "موقع تقريبي ضمن نحو 1000 م"
    assert body["public"]["meaning"] == "capture_point"
    assert body["public"]["cell"]["type"] == "Polygon"
    # The label comes from the public point, and is the nearest populated place.
    assert body["place"]["geoname_id"] == TUNIS_CITY
    assert body["place"]["label"] == "تونس"
    assert body["place"]["country_iso2"] == "TN"
    point = await db_session.get(MapCapturePoint, int(body["id"]))
    assert point is not None and (point.latitude, point.longitude) == EXACT
    entry = await db_session.get(MapEntry, int(body["id"]))
    assert entry is not None and (entry.public_lat, entry.public_lng) == (centre.lat, centre.lng)


async def test_only_the_owner_s_pipeline_insight_can_be_placed(
    db_session, make_member, make_insight, world
):
    author = await make_member("author")
    other = await make_member("other")
    insight_id = await _insight(db_session, author)
    demo_id = await _insight(db_session, author, engine="demo")

    assert (await _place(other, insight_id)).status_code == 404
    refused = await _place(author, demo_id)
    assert (refused.status_code, refused.json()["error"]) == (409, "INSIGHT_NOT_PUBLISHABLE")
    assert (await _place(author, insight_id + 1)).status_code == 404


async def test_placing_needs_a_verified_address_and_a_public_identity(
    db_session, make_member, make_insight, world
):
    unverified = await make_member("fresh", verified=False)
    nameless = await make_member("nameless", identity=False)
    guest = await make_member(signed_in=False)
    insight_id = await _insight(db_session, unverified)

    assert (await _place(unverified, insight_id)).status_code == 403
    assert (await _place(nameless, insight_id)).status_code == 409
    assert (await guest.http.get("/me/map-entries")).status_code == 401


async def test_a_bad_point_is_refused_before_anything_is_stored(
    db_session, make_member, make_insight, world
):
    author = await make_member("author")
    insight_id = await _insight(db_session, author)

    assert (await _place(author, insight_id, latitude=91)).status_code == 422
    assert (await _place(author, insight_id, source="guess")).status_code == 422
    assert (await _place(author, insight_id, accuracy_m=-1)).status_code == 422
    assert await db_session.scalar(select(MapEntry)) is None


async def test_publishing_and_withdrawing_follow_the_states(
    db_session, make_member, make_insight, world
):
    author = await make_member("author")
    insight_id = await _insight(db_session, author)

    # Nothing to publish before a point is placed.
    assert (await author.http.post(f"/insights/{insight_id}/map/publish")).status_code == 404
    entry_id = await _published(author, insight_id)
    assert (await author.http.post(f"/insights/{insight_id}/map/publish")).status_code == 409
    mine = await author.http.get("/me/map-entries")
    assert [item["status"] for item in mine.json()] == ["published"]

    # Placing again changes what is shown, so the entry is a draft again.
    moved = await _place(author, insight_id, latitude=36.80, longitude=10.18)
    assert moved.json()["status"] == "draft"
    assert (await author.http.get(f"/atlas/entries/{entry_id}")).status_code == 404

    assert (await author.http.delete(f"/insights/{insight_id}/map")).status_code == 204
    gone = await author.http.get(f"/atlas/entries/{entry_id}")
    assert (gone.status_code, gone.json()["error"]) == (410, "GONE")
    assert await db_session.get(MapCapturePoint, int(entry_id)) is None
    entry = await db_session.get(MapEntry, int(entry_id))
    assert entry is not None and entry.status.value == "withdrawn"
    assert (entry.public_lat, entry.public_lng, entry.public_geom) == (None, None, None)
    withdrawn = await author.http.get(f"/insights/{insight_id}/map")
    assert withdrawn.json()["capture"] is None and withdrawn.json()["public"] is None
    # Withdrawing again changes nothing.
    assert (await author.http.delete(f"/insights/{insight_id}/map")).status_code == 204


# ─── The public side ───


async def test_the_map_window_shows_the_cell_centre_and_never_the_exact_point(
    db_session, make_member, make_insight, world
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    entry_id = await _published(author, await _insight(db_session, author))
    draft_id = await _insight(db_session, author)
    assert (await _place(author, draft_id)).status_code == 200

    window = {"west": 10.0, "south": 36.5, "east": 10.5, "north": 37.0}
    response = await guest.http.get("/atlas/entries", params=window)

    assert response.status_code == 200, response.text
    assert_public(response)
    body = response.json()
    assert body["type"] == "FeatureCollection" and body["truncated"] is False
    assert [feature["id"] for feature in body["features"]] == [entry_id]
    feature = body["features"][0]
    centre = approximate(*EXACT, CELL_M)
    assert feature["geometry"] == {"type": "Point", "coordinates": [centre.lng, centre.lat]}
    assert feature["properties"]["author"] == {"handle": "author", "public_name": "author name"}
    assert feature["properties"]["place"]["label"] == "تونس"
    assert feature["properties"]["title"] == "الحياة في قطرة"
    # Outside the window: nothing.
    elsewhere = await guest.http.get(
        "/atlas/entries", params={"west": 39.0, "south": 21.0, "east": 40.0, "north": 22.0}
    )
    assert elsewhere.json()["features"] == []


async def test_the_window_filters_and_crosses_the_antimeridian(
    db_session, make_member, make_insight, world
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    tunis = await _published(author, await _insight(db_session, author, entity_ids=["rain"]))
    far_id = await _insight(db_session, author, entity_ids=["tree"])
    assert (await _place(author, far_id, latitude=0.5, longitude=179.9)).status_code == 200
    far = str((await author.http.post(f"/insights/{far_id}/map/publish")).json()["id"])

    whole = {"west": -180, "south": -90, "east": 180, "north": 90}
    assert {
        f["id"] for f in (await guest.http.get("/atlas/entries", params=whole)).json()["features"]
    } == {tunis, far}
    by_concept = await guest.http.get("/atlas/entries", params={**whole, "concept": "rain"})
    assert [f["id"] for f in by_concept.json()["features"]] == [tunis]
    by_country = await guest.http.get("/atlas/entries", params={**whole, "country": "tn"})
    assert [f["id"] for f in by_country.json()["features"]] == [tunis]
    since = await guest.http.get(
        "/atlas/entries", params={**whole, "since": "2099-01-01T00:00:00Z"}
    )
    assert since.json()["features"] == []
    # A window that crosses the antimeridian: west > east.
    crossing = await guest.http.get(
        "/atlas/entries", params={"west": 179, "south": -1, "east": -179, "north": 1}
    )
    assert [f["id"] for f in crossing.json()["features"]] == [far]
    limited = await guest.http.get("/atlas/entries", params={**whole, "limit": 1})
    assert len(limited.json()["features"]) == 1 and limited.json()["truncated"] is True
    assert (
        await guest.http.get("/atlas/entries", params={**whole, "east": 181})
    ).status_code == 422
    assert (
        await guest.http.get("/atlas/entries", params={**whole, "country": "tun"})
    ).status_code == 422


async def test_an_entry_s_page_shows_the_insight_by_reference_and_its_place(
    db_session, make_member, make_insight, world
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    insight_id = await _insight(
        db_session,
        author,
        quran_surah=112,
        quran_ayah=1,
        hadith_collection="bukhari",
        hadith_number="1",
    )
    entry_id = await _published(author, insight_id)

    response = await guest.http.get(f"/atlas/entries/{entry_id}")

    assert response.status_code == 200, response.text
    assert_public(response)
    body = response.json()
    assert body["insight_id"] == str(insight_id)
    assert body["title"] == "الحياة في قطرة"
    assert body["explanation"] == "قطرات على ورق نبتة."
    assert body["step"] == "احفظ الدعاء الوارد في الحديث."
    assert body["author"]["handle"] == "author"
    assert body["location"]["point"]["coordinates"] == list(approximate(*EXACT, CELL_M))[::-1]
    assert body["location"]["meaning_label"] == "موضع الالتقاط، تقريبًا"
    assert body["place"]["geoname_id"] == TUNIS_CITY
    assert [verse["ayah"] for verse in body["quran"]] == [1]
    assert [hadith["number"] for hadith in body["hadith"]] == ["1"]
    assert body["post_id"] is None
    # The verse is shown exactly as stored, with its hash.
    verse = body["quran"][0]
    assert verse["verified"] is True and len(verse["sha256"]) == 64

    assert (await guest.http.get(f"/atlas/entries/{int(entry_id) + 1}")).status_code == 404


async def test_a_place_page_lists_its_entries_newest_first_with_a_cursor(
    db_session, make_member, make_insight, world
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    first = await _published(author, await _insight(db_session, author))
    second = await _published(author, await _insight(db_session, author))

    page = await guest.http.get(f"/atlas/places/{TUNIS_CITY}", params={"limit": 1})

    assert page.status_code == 200, page.text
    assert_public(page)
    body = page.json()
    assert body["place"]["label"] == "تونس"
    # The place's own point, from GeoNames: a public place, not any owner's.
    lng, lat = body["point"]["coordinates"]
    assert (
        body["point"]["type"] == "Point" and abs(lat - TUNIS[0]) < 0.1 and abs(lng - TUNIS[1]) < 0.1
    )
    assert [entry["id"] for entry in body["entries"]] == [second]
    assert body["next_cursor"] is not None
    rest = await guest.http.get(
        f"/atlas/places/{TUNIS_CITY}", params={"limit": 1, "cursor": body["next_cursor"]}
    )
    assert [entry["id"] for entry in rest.json()["entries"]] == [first]
    assert rest.json()["next_cursor"] is None
    assert (await guest.http.get("/atlas/places/999")).status_code == 404


async def test_a_blocked_or_nameless_author_and_a_switched_off_atlas_show_nothing(
    db_session, make_member, make_insight, world, account_app
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    entry_id = await _published(author, await _insight(db_session, author))
    author.user.is_active = False
    await db_session.flush()
    whole = {"west": -180, "south": -90, "east": 180, "north": 90}

    assert (await guest.http.get("/atlas/entries", params=whole)).json()["features"] == []
    assert (await guest.http.get(f"/atlas/entries/{entry_id}")).status_code == 404

    author.user.is_active = True
    await db_session.flush()
    settings = account_app.state.settings
    account_app.state.settings = settings.model_copy(update={"feature_atlas": False})
    try:
        off = await guest.http.get("/atlas/entries", params=whole)
        assert (off.status_code, off.json()["error"]) == (404, "FEATURE_DISABLED")
    finally:
        account_app.state.settings = settings


async def test_a_map_entry_can_be_reported_but_not_one_s_own_nor_a_draft(
    db_session, make_member, make_insight, world
):
    author = await make_member("author")
    reader = await make_member("reader")
    entry_id = await _published(author, await _insight(db_session, author))
    draft_id = await _insight(db_session, author)
    assert (await _place(author, draft_id)).status_code == 200
    draft_entry = (await author.http.get(f"/insights/{draft_id}/map")).json()["id"]

    def report(member: Member, target: str, reason: str = "wrong_place") -> Any:
        return member.http.post(
            "/reports", json={"target_type": "map_entry", "target_id": target, "reason": reason}
        )

    filed = await report(reader, entry_id)
    assert filed.status_code == 201, filed.text
    again = await report(reader, entry_id, "private_information")
    assert again.json()["id"] == filed.json()["id"]
    assert (await report(author, entry_id)).status_code == 400
    assert (await report(reader, draft_entry)).status_code == 404
    # A reported entry stays on the map until a moderator decides: no automatic hold.
    assert (await reader.http.get(f"/atlas/entries/{entry_id}")).status_code == 200


async def test_the_export_carries_the_owner_s_entries_with_their_exact_points(
    db_session, make_member, make_insight, world
):
    author = await make_member("author")
    entry_id = await _published(author, await _insight(db_session, author))

    export = await author.http.get("/account/export")

    assert export.status_code == 200
    entries = export.json()["map_entries"]
    assert [entry["id"] for entry in entries] == [entry_id]
    assert (entries[0]["capture"]["latitude"], entries[0]["capture"]["longitude"]) == EXACT


async def test_the_sitemap_lists_a_place_once_it_has_a_published_entry(
    db_session, make_member, make_insight, world
):
    author = await make_member("author")
    provider = sitemap_service.PROVIDERS[Section.PLACES]
    assert await provider.pages(db_session, 10) == []

    await _published(author, await _insight(db_session, author))

    pages = await provider.pages(db_session, 10)
    assert [page.page for page in pages] == [0]
    assert isinstance(pages[0].lastmod, datetime) and pages[0].lastmod.tzinfo is not None
    entries = await provider.entries(db_session, 0, 10)
    assert [entry.path for entry in entries] == [f"/atlas/places/{TUNIS_CITY}"]
    assert entries[0].lastmod >= datetime(2026, 1, 1, tzinfo=UTC)


def test_public_schemas_have_no_field_for_a_private_location():
    """Adding a private field to a public schema fails here until it is justified."""
    from src.schemas import atlas

    public = (
        atlas.AtlasFeatureProperties,
        atlas.AtlasFeature,
        atlas.AtlasFeatureCollection,
        atlas.AtlasEntryOut,
        atlas.AtlasPlaceOut,
        atlas.PublicLocationOut,
        atlas.PlaceRef,
    )
    for schema in public:
        assert not (set(schema.model_fields) & PRIVATE_KEYS), schema.__name__
