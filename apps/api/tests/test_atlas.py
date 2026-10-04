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
from src.models import HadithClassification, MapCapturePoint, MapEntry
from src.owner import Owner
from src.scripture.rulings import RulingInput, find_hadith, record_ruling
from src.scripture.text import sha256_hex
from src.services import atlas_service, sitemap_service
from src.services import cursor as cursors
from src.services.sitemap_service import Section
from tests import geo_dataset as world_data
from tests.geo_dataset import TUNIS, TUNIS_CITY
from tests.scans.builders import insight_row, scan_row
from tests.scripture.fixtures import hadith_text, verse_text
from tests.support_social import Member

# Where the owner says the photo was taken: a point inside Tunis, given to the exact metre.
EXACT = (36.806512, 10.181534)
CELL_M = 1000
# No private field, and no timestamp: an insight id or a time to the second would say when the
# photo was taken or when its owner was there.
PRIVATE_KEYS = {
    "latitude",
    "longitude",
    "capture",
    "accuracy_m",
    "captured_at",
    "measured_at",
    "insight_id",
    "published_at",
    "created_at",
}


# What the fixture store holds with an eligible ruling: 112:1 and bukhari 1 (صحيح); bukhari 8 is ضعيف
# and bukhari 1032 has no ruling at all.
EVIDENCE: dict[str, Any] = {
    "quran_surah": 112,
    "quran_ayah": 1,
    "hadith_collection": "bukhari",
    "hadith_number": "1",
    "explanation": [
        {"section": "seen", "text": "قطرات على ورق نبتة.", "sources": []},
        {"section": "sunnah", "text": "[ما يضيفه الحديث]", "sources": ["hadith:bukhari:1"]},
    ],
    "small_step": {
        "text": "احفظ الدعاء الوارد في الحديث.",
        "kind": "text_grounded",
        "grounded_in": ["hadith:bukhari:1"],
    },
}


async def _insight(db: AsyncSession, member: Member, **values: Any) -> int:
    owner = Owner(user_id=member.user.id)
    scan = scan_row(owner)
    db.add(scan)
    await db.flush()
    insight = insight_row(owner, scan_id=scan.id, **{**EVIDENCE, **values})
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


def coordinates_of(value: Any) -> list[list[float]]:
    """Every GeoJSON point in a document."""
    found: list[list[float]] = []
    if isinstance(value, dict):
        if value.get("type") == "Point" and isinstance(value.get("coordinates"), list):
            found.append(value["coordinates"])
        for child in value.values():
            found += coordinates_of(child)
    elif isinstance(value, list):
        for child in value:
            found += coordinates_of(child)
    return found


def assert_public(response: Any) -> None:
    """
    A public answer holds neither the exact point nor any field that could name one.

    Every point in it is the centre of an approximation cell: rounding it again changes nothing.
    """
    body = response.json()
    assert not (keys_of(body) & PRIVATE_KEYS), keys_of(body) & PRIVATE_KEYS
    assert str(EXACT[0]) not in response.text
    assert str(EXACT[1]) not in response.text
    for lng, lat in coordinates_of(body):
        if (lng, lat) != (TUNIS[1], TUNIS[0]) and "place" not in body:
            assert tuple(approximate(lat, lng, CELL_M)) == (lat, lng), (lat, lng)


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
    # The other owner-only routes answer the same for an insight that is not one's own.
    assert (await _place(author, insight_id)).status_code == 200
    assert (await other.http.get(f"/insights/{insight_id}/map")).status_code == 404
    assert (await other.http.post(f"/insights/{insight_id}/map/publish")).status_code == 404
    assert (await other.http.delete(f"/insights/{insight_id}/map")).status_code == 404
    assert (await author.http.get(f"/insights/{insight_id}/map")).status_code == 200


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
    assert (await _place(guest, insight_id)).status_code == 401


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

    assert (await author.http.delete(f"/insights/{insight_id}/map")).status_code == 204
    gone = await author.http.get(f"/atlas/entries/{entry_id}")
    assert (gone.status_code, gone.json()["error"]) == (410, "GONE")
    assert await db_session.get(MapCapturePoint, int(entry_id)) is None
    entry = await db_session.get(MapEntry, int(entry_id))
    assert entry is not None and entry.status.value == "withdrawn"
    assert (entry.public_lat, entry.public_lng, entry.public_geom) == (None, None, None)
    # Nothing of the location survives the tombstone: not even the place it was labelled with.
    assert (entry.place_geoname_id, entry.place_label, entry.country_iso2) == (None, None, None)
    # The owner still sees the withdrawn entry in the list, with nothing of its location left.
    withdrawn = (await author.http.get("/me/map-entries")).json()
    assert [(item["status"], item["public"], item["place"]) for item in withdrawn] == [
        ("withdrawn", None, None)
    ]
    # The owner has no live entry any more; withdrawing again changes nothing.
    assert (await author.http.get(f"/insights/{insight_id}/map")).status_code == 404
    assert (await author.http.delete(f"/insights/{insight_id}/map")).status_code == 204

    # Placing the insight again gives it a new address; the old one stays gone.
    again = await _place(author, insight_id)
    assert again.status_code == 200 and again.json()["id"] != entry_id
    assert (await author.http.get(f"/atlas/entries/{entry_id}")).status_code == 410
    new_id = str(again.json()["id"])
    assert (await author.http.post(f"/insights/{insight_id}/map/publish")).status_code == 200
    # Placing a published entry again changes what is shown, so it is a draft again, off the map.
    moved = await _place(author, insight_id, latitude=36.80, longitude=10.18)
    assert moved.json()["status"] == "draft" and moved.json()["id"] == new_id
    assert (await author.http.get(f"/atlas/entries/{new_id}")).status_code == 404
    # The address was shared once: withdrawing the re-placed draft still leaves the tombstone.
    assert (await author.http.delete(f"/insights/{insight_id}/map")).status_code == 204
    gone_again = await author.http.get(f"/atlas/entries/{new_id}")
    assert (gone_again.status_code, gone_again.json()["error"]) == (410, "GONE")
    tombstone = await db_session.get(MapEntry, int(new_id))
    assert tombstone is not None and tombstone.status.value == "withdrawn"
    assert (tombstone.public_lat, tombstone.place_label) == (None, None)
    assert await db_session.get(MapCapturePoint, int(new_id)) is None


async def test_a_draft_withdrawn_before_it_was_public_leaves_nothing_behind(
    db_session, make_member, make_insight, world
):
    author = await make_member("author")
    insight_id = await _insight(db_session, author)
    draft_id = (await _place(author, insight_id)).json()["id"]

    assert (await author.http.delete(f"/insights/{insight_id}/map")).status_code == 204

    # An id that was never public says nothing: 404, not 410.
    assert (await author.http.get(f"/atlas/entries/{draft_id}")).status_code == 404
    assert await db_session.get(MapEntry, int(draft_id)) is None


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
    since = await guest.http.get("/atlas/entries", params={**whole, "since": "2099-01-01"})
    assert since.json()["features"] == []
    # The filter takes a day, never a time.
    assert (
        await guest.http.get("/atlas/entries", params={**whole, "since": "2026-10-04T10:00:00Z"})
    ).status_code == 422
    # And what comes back is a day, never a time.
    feature = (await guest.http.get("/atlas/entries", params=whole)).json()["features"][0]
    assert len(feature["properties"]["published_on"]) == 10
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
    insight_id = await _insight(db_session, author)
    entry_id = await _published(author, insight_id)

    response = await guest.http.get(f"/atlas/entries/{entry_id}")

    assert response.status_code == 200, response.text
    assert_public(response)
    body = response.json()
    assert body["title"] == "الحياة في قطرة"
    assert body["explanation"] == "قطرات على ورق نبتة. [ما يضيفه الحديث]"
    assert body["step"] == "احفظ الدعاء الوارد في الحديث."
    assert body["author"]["handle"] == "author"
    assert body["location"]["point"]["coordinates"] == list(approximate(*EXACT, CELL_M))[::-1]
    assert body["location"]["meaning_label"] == "موضع الالتقاط، تقريبًا"
    assert body["place"]["geoname_id"] == TUNIS_CITY
    assert [verse["ayah"] for verse in body["quran"]] == [1]
    assert [hadith["number"] for hadith in body["hadith"]] == ["1"]
    assert body["post_id"] is None
    assert len(body["published_on"]) == 10
    # The verse and the hadith are shown exactly as stored, with the hash of what is shown.
    verse = body["quran"][0]
    assert verse["text"] == verse_text(112, 1)
    assert verse["sha256"] == sha256_hex(verse["text"])
    hadith = body["hadith"][0]
    assert hadith["text"] == hadith_text("bukhari", 1)
    assert hadith["sha256"] == sha256_hex(hadith["text"])
    assert hadith["classification"] == "صحيح" and hadith["verification_url"].startswith(
        "https://dorar.net/"
    )

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
    # The cursor carries the day of publication and the id, never the hour.
    position = cursors.decode(body["next_cursor"])
    assert position is not None and position.at.astimezone(UTC).timetuple()[3:6] == (0, 0, 0)
    assert position.id == int(second)
    rest = await guest.http.get(
        f"/atlas/places/{TUNIS_CITY}", params={"limit": 1, "cursor": body["next_cursor"]}
    )
    assert [entry["id"] for entry in rest.json()["entries"]] == [first]
    assert rest.json()["next_cursor"] is None
    assert (await guest.http.get("/atlas/places/999")).status_code == 404
    # Nothing of the atlas is cached: the answer depends on the viewer, and a withdrawal must
    # leave every cache at once.
    for response in (page, rest):
        assert response.headers["cache-control"] == "no-store"


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


async def test_a_map_entry_is_reported_while_the_atlas_alone_is_on_and_never_while_it_is_off(
    db_session, make_member, make_insight, world, account_app, guard
):
    from tests.support_social import publish_post

    author = await make_member("author")
    reader = await make_member("reader")
    entry_id = await _published(author, await _insight(db_session, author))
    post_id = await publish_post(author, make_insight)
    settings = account_app.state.settings

    def report(target_type: str, target: str) -> Any:
        return reader.http.post(
            "/reports",
            json={"target_type": target_type, "target_id": target, "reason": "private_information"},
        )

    try:
        account_app.state.settings = settings.model_copy(update={"feature_social": False})
        filed = await report("map_entry", entry_id)
        assert filed.status_code == 201, filed.text
        # The network is off: its posts are not there to be reported, nor said to exist.
        assert (await report("post", post_id)).status_code == 404

        account_app.state.settings = settings.model_copy(update={"feature_atlas": False})
        assert (await report("post", post_id)).status_code == 201
        assert (await report("map_entry", entry_id)).status_code == 404

        account_app.state.settings = settings.model_copy(
            update={"feature_social": False, "feature_atlas": False}
        )
        assert (await report("map_entry", entry_id)).status_code == 404
    finally:
        account_app.state.settings = settings


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
    # A day, never the hour: the sitemap says no more than the place page does.
    for stamp in (pages[0].lastmod, entries[0].lastmod):
        assert stamp.astimezone(UTC).timetuple()[3:6] == (0, 0, 0), stamp


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


# ─── The scripture rule: nothing is shown or published that rests on a text not shown ───


async def test_an_insight_without_eligible_evidence_cannot_be_placed(
    db_session, make_member, make_insight, world
):
    author = await make_member("author")
    weak = await _insight(db_session, author, hadith_number="8")
    unruled = await _insight(db_session, author, hadith_number="1032")
    missing_verse = await _insight(db_session, author, quran_surah=2, quran_ayah=999)
    nothing = await _insight(
        db_session,
        author,
        quran_surah=None,
        quran_ayah=None,
        hadith_collection=None,
        hadith_number=None,
        explanation=[{"section": "seen", "text": "x", "sources": []}],
        small_step=None,
    )

    for insight_id in (weak, unruled, missing_verse, nothing):
        response = await _place(author, insight_id)
        assert (response.status_code, response.json()["error"]) == (
            409,
            "INSIGHT_NOT_PUBLISHABLE",
        ), response.text
    assert await db_session.scalar(select(MapEntry)) is None


async def test_a_hadith_whose_ruling_changes_leaves_the_page_with_what_rested_on_it(
    db_session, make_member, make_insight, world
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    insight_id = await _insight(db_session, author)
    entry_id = await _published(author, insight_id)

    hadith = await find_hadith(db_session, "bukhari", "1")
    assert hadith is not None
    await record_ruling(
        db_session,
        hadith.id,
        RulingInput(
            ruling_text="[ضعيف]",
            scholar="s",
            source_book="b",
            page="2",
            dorar_url="https://dorar.net/h/y",
            classification=HadithClassification.DAIF,
            editor_name="editor",
        ),
    )

    body = (await guest.http.get(f"/atlas/entries/{entry_id}")).json()
    assert body["hadith"] == []
    assert [verse["ayah"] for verse in body["quran"]] == [1]
    # The sunnah part and the step rested on the hadith: gone with it; the verse's own line stays.
    assert body["explanation"] == "قطرات على ورق نبتة."
    assert body["step"] is None
    # And placing it again, or publishing it again, is refused until the ruling allows it.
    assert (await _place(author, insight_id)).status_code == 409


async def test_a_block_hides_the_atlas_both_ways(db_session, make_member, make_insight, world):
    author = await make_member("author")
    reader = await make_member("reader")
    guest = await make_member(signed_in=False)
    entry_id = await _published(author, await _insight(db_session, author))
    whole = {"west": -180, "south": -90, "east": 180, "north": 90}
    assert (await reader.http.put("/blocks/author")).status_code == 204

    assert (await reader.http.get("/atlas/entries", params=whole)).json()["features"] == []
    assert (await reader.http.get(f"/atlas/entries/{entry_id}")).status_code == 404
    assert (await reader.http.get(f"/atlas/places/{TUNIS_CITY}")).status_code == 404
    # The one who was blocked does not see the other either; everyone else still does.
    reader_entry = await _published(reader, await _insight(db_session, reader))
    assert (await author.http.get(f"/atlas/entries/{reader_entry}")).status_code == 404
    assert (await guest.http.get(f"/atlas/entries/{entry_id}")).status_code == 200


async def test_an_account_that_said_it_is_under_13_places_nothing(
    db_session, make_member, make_insight, world
):
    author = await make_member("author")
    insight_id = await _insight(db_session, author)
    assert (await author.http.patch("/profile", json={"age_range": "under_13"})).status_code == 200

    refused = await _place(author, insight_id)

    assert (refused.status_code, refused.json()["error"]) == (409, "UNDER_13_CANNOT_PUBLISH")


async def test_a_text_that_reads_like_scripture_is_never_placed(
    db_session, make_member, make_insight, world
):
    author = await make_member("author")
    insight_id = await _insight(db_session, author, title=verse_text(112, 1))

    refused = await _place(author, insight_id)

    assert (refused.status_code, refused.json()["error"]) == (409, "INSIGHT_NOT_PUBLISHABLE")


async def test_enough_reports_hide_an_entry_until_a_moderator_decides(
    db_session, make_member, make_insight, world
):
    from src.services import moderation_service

    author = await make_member("author")
    reporters = [await make_member(f"reader{n}") for n in range(3)]
    insight_id = await _insight(db_session, author)
    entry_id = await _published(author, insight_id)
    whole = {"west": -180, "south": -90, "east": 180, "north": 90}

    for reporter in reporters:
        filed = await reporter.http.post(
            "/reports",
            json={
                "target_type": "map_entry",
                "target_id": entry_id,
                "reason": "private_information",
            },
        )
        assert filed.status_code == 201, filed.text

    # Hidden from everyone at the threshold, and its owner is told why.
    assert (await reporters[0].http.get(f"/atlas/entries/{entry_id}")).status_code == 404
    assert (await reporters[0].http.get("/atlas/entries", params=whole)).json()["features"] == []
    mine = (await author.http.get(f"/insights/{insight_id}/map")).json()
    assert mine["status"] == "pending_review"
    assert mine["status_message"] == "وصلتنا عنه بلاغات، فأُخفي مؤقتًا حتى يراجعه مشرف."
    # Nor can the owner place it again to slip past the decision.
    assert (await _place(author, insight_id)).status_code == 409

    # A moderator approves: back on the map, reports dismissed.
    entry = await db_session.get(MapEntry, int(entry_id))
    assert entry is not None
    await moderation_service.approve(db_session, entry, reporters[0].user.id)
    await db_session.flush()
    assert (await reporters[0].http.get(f"/atlas/entries/{entry_id}")).status_code == 200
    # A moderator removes: gone for everyone but the owner, who sees the reason.
    await moderation_service.remove(db_session, entry, reporters[0].user.id, "private_information")
    await db_session.flush()
    assert (await reporters[0].http.get(f"/atlas/entries/{entry_id}")).status_code == 404
    mine = (await author.http.get(f"/insights/{insight_id}/map")).json()
    assert mine["status"] == "removed" and "معلومات خاصة" in mine["status_message"]
    assert (await _place(author, insight_id)).status_code == 409


# ─── Rows the normal flow never leaves behind ───


async def test_withdrawing_an_entry_whose_exact_point_is_already_gone(
    db_session, make_member, make_insight, world
):
    author = await make_member("author")
    insight_id = await _insight(db_session, author)
    entry_id = await _published(author, insight_id)
    point = await db_session.get(MapCapturePoint, int(entry_id))
    assert point is not None
    await db_session.delete(point)
    await db_session.flush()

    assert (await author.http.delete(f"/insights/{insight_id}/map")).status_code == 204

    entry = await db_session.get(MapEntry, int(entry_id))
    assert entry is not None and entry.status.value == "withdrawn"
    assert (entry.public_lat, entry.public_lng) == (None, None)


async def test_an_entry_page_without_a_public_point_is_not_found(
    db_session, make_member, make_insight, world, monkeypatch
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    entry_id = await _published(author, await _insight(db_session, author))
    # A published row always has its public point; should one ever lose it, the page says nothing.
    monkeypatch.setattr(atlas_service, "public_location", lambda entry: None)

    response = await guest.http.get(f"/atlas/entries/{entry_id}")

    assert response.status_code == 404
    assert_public(response)


async def test_a_place_page_whose_entries_lost_their_label_is_not_found(
    db_session, make_member, make_insight, world
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    entry_id = await _published(author, await _insight(db_session, author))
    entry = await db_session.get(MapEntry, int(entry_id))
    assert entry is not None and entry.place_geoname_id == TUNIS_CITY
    entry.place_label = None
    await db_session.flush()

    response = await guest.http.get(f"/atlas/places/{TUNIS_CITY}")

    assert response.status_code == 404
    assert_public(response)
