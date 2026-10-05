"""
The atlas answers that keep a map light: the entries grouped by grid cell, and a paginated list.

Guarded here: the zoom at which grouping stops, true counts after the filters and the blocks,
the box and the mean of public points, a lone entry shown as an entry, the antimeridian and the
poles, the cap and `truncated`, the order by distance with a keyset cursor whose pages neither
skip nor repeat, the total, and that neither answer holds an exact point, an id of an entry
inside a group, an author or a time.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError

from src.errors import AppError, ErrorCode
from src.features import FeatureFlag
from src.geo.privacy import approximate
from src.models import MapEntrySponsorship, MapEntryStatus
from src.services import atlas_service
from src.services import cursor as cursors
from tests import geo_dataset as world_data
from tests.helpers import switched
from tests.support_orphans import entry_row
from tests.test_atlas import CELL_M, EXACT, _insight, _place, keys_of

WHOLE = {"west": -180, "south": -90, "east": 180, "north": 90}
TUNIS_WINDOW = {"west": 9.0, "south": 36.0, "east": 11.5, "north": 38.0}
CLUSTER_KEYS = {"kind", "id", "count", "bbox"}


@pytest.fixture
async def world(db_session, scripture):
    await world_data.load_world(db_session)


async def _at(db, member, lat: float, lng: float, **values) -> str:
    """Publish an entry of `member` placed at a point; its public id."""
    insight_id = await _insight(db, member, **values)
    assert (await _place(member, insight_id, latitude=lat, longitude=lng)).status_code == 200
    response = await member.http.post(f"/insights/{insight_id}/map/publish")
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


def _public(lat: float, lng: float) -> tuple[float, float]:
    centre = approximate(lat, lng, CELL_M)
    return centre.lat, centre.lng


async def _clusters(client, zoom: int, **params):
    return await client.http.get("/atlas/clusters", params={**WHOLE, "zoom": zoom, **params})


def _kinds(response) -> list[str]:
    return [f["properties"]["kind"] for f in response.json()["features"]]


# ─── Grouping ───


def test_a_cell_is_about_sixty_pixels_wide_at_every_zoom():
    for zoom in (0, 3, 10, 15):
        across, cell_m = atlas_service._grid(zoom)
        assert cell_m == pytest.approx(60 * 156543.03392 / 2**zoom, rel=0.15)
        assert across * cell_m == pytest.approx(2 * 20037508.342789244)
    assert atlas_service._grid(0)[0] == 4
    assert atlas_service.CLUSTER_OFF_ZOOM == 16


async def test_entries_of_one_cell_make_a_group_with_a_count_a_box_and_a_mean(
    db_session, make_member, world
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    points = [(36.8065, 10.1815), (36.85, 10.2), (36.9, 10.3)]
    for lat, lng in points:
        await _at(db_session, author, lat, lng)
    lone = await _at(db_session, author, 0.5, 100.5, entity_ids=["tree"])

    response = await _clusters(guest, 6)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["type"] == "FeatureCollection" and body["truncated"] is False
    group, single = body["features"]
    assert group["properties"]["kind"] == "cluster" and group["properties"]["count"] == 3
    # Nothing but a count, a box and a cell: no id of an entry, no author, no time.
    assert set(group["properties"]) == CLUSTER_KEYS
    assert keys_of(group) == CLUSTER_KEYS | {"type", "geometry", "properties", "coordinates"}
    publics = [_public(lat, lng) for lat, lng in points]
    lats, lngs = [p[0] for p in publics], [p[1] for p in publics]
    assert group["properties"]["bbox"] == [min(lngs), min(lats), max(lngs), max(lats)]
    mean_lng, mean_lat = group["geometry"]["coordinates"]
    assert mean_lat == pytest.approx(sum(lats) / 3) and mean_lng == pytest.approx(sum(lngs) / 3)
    assert group["properties"]["id"].startswith("6:")
    # The lone entry of its cell is a point like any other.
    assert single["properties"]["kind"] == "entry" and single["id"] == lone
    assert single["properties"]["title"] == "الحياة في قطرة"
    assert single["properties"]["author"] == {"handle": "author", "public_name": "author name"}
    assert single["geometry"]["coordinates"] == list(reversed(_public(0.5, 100.5)))
    # The exact point of the first photo is nowhere in the answer.
    assert str(EXACT[0]) not in response.text and str(EXACT[1]) not in response.text


async def test_the_cell_id_is_stable_and_changes_with_the_zoom(db_session, make_member, world):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    for _ in range(2):
        await _at(db_session, author, *EXACT)

    first = (await _clusters(guest, 12)).json()["features"][0]["properties"]["id"]
    again = (await _clusters(guest, 12)).json()["features"][0]["properties"]["id"]
    other = (await _clusters(guest, 13)).json()["features"][0]["properties"]["id"]

    assert first == again != other


async def test_nothing_is_grouped_from_the_last_zoom_on(db_session, make_member, world):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    ids = {await _at(db_session, author, *EXACT) for _ in range(2)}

    grouped = await _clusters(guest, atlas_service.CLUSTER_OFF_ZOOM - 1)
    open_ = await _clusters(guest, atlas_service.CLUSTER_OFF_ZOOM)

    # The two share a public point: one group just below the threshold, two entries at it.
    assert (
        _kinds(grouped) == ["cluster"] and grouped.json()["features"][0]["properties"]["count"] == 2
    )
    assert _kinds(open_) == ["entry", "entry"]
    assert {f["id"] for f in open_.json()["features"]} == ids
    assert all(
        set(f["properties"]) >= {"kind", "title", "cell_m"} for f in open_.json()["features"]
    )


async def test_a_cell_left_with_one_entry_is_an_entry_again(db_session, make_member, world):
    first = await make_member("first")
    second = await make_member("second")
    reader = await make_member("reader")
    await _at(db_session, first, *EXACT)
    await _at(db_session, second, *EXACT)
    assert (await reader.http.put("/blocks/second")).status_code == 204

    seen = await _clusters(reader, 12)
    assert _kinds(seen) == ["entry"]
    assert seen.json()["features"][0]["properties"]["author"]["handle"] == "first"
    assert (await reader.http.delete("/blocks/second")).status_code == 204
    assert (await _clusters(reader, 12)).json()["features"][0]["properties"]["count"] == 2


async def test_blocks_reduce_the_counts_both_ways_and_the_filters_apply(
    db_session, make_member, world
):
    author = await make_member("author")
    other = await make_member("other")
    reader = await make_member("reader")
    guest = await make_member(signed_in=False)
    for _ in range(2):
        await _at(db_session, author, *EXACT, entity_ids=["rain"])
    await _at(db_session, other, *EXACT, entity_ids=["tree"])
    await _at(db_session, other, -33.9, 151.2, entity_ids=["rain"])

    def counts(response):
        return sorted(f["properties"].get("count", 1) for f in response.json()["features"])

    assert counts(await _clusters(guest, 8)) == [1, 3]
    assert counts(await _clusters(guest, 8, concept="rain")) == [1, 2]
    assert counts(await _clusters(guest, 8, concept="tree")) == [1]
    assert counts(await _clusters(guest, 8, country="tn")) == [3]
    assert counts(await _clusters(guest, 8, country="FR")) == []
    assert counts(await _clusters(guest, 8, since="2999-01-01")) == []
    assert counts(await _clusters(guest, 8, since="2000-01-01")) == [1, 3]
    assert counts(await _clusters(guest, 8, **TUNIS_WINDOW)) == [3]

    assert (await reader.http.put("/blocks/author")).status_code == 204
    assert counts(await _clusters(reader, 8)) == [1, 1]
    # The one who was blocked sees the blocker's entries no more than the blocker does theirs.
    assert (await author.http.put("/blocks/other")).status_code == 204
    assert counts(await _clusters(author, 8)) == [2]


async def test_the_window_can_cross_the_antimeridian_and_a_group_never_spans_it(
    db_session, make_member, world
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    east = await _at(db_session, author, 0.5, 179.9)
    west = await _at(db_session, author, 0.5, -179.9)
    await _at(db_session, author, *EXACT)

    window = {"west": 170, "south": -10, "east": -170, "north": 10}
    response = await _clusters(guest, 3, **window)

    assert {f["id"] for f in response.json()["features"]} == {east, west}
    assert _kinds(response) == ["entry", "entry"]
    # Both sides in one cell would have made a mean near longitude zero.
    assert all(abs(f["geometry"]["coordinates"][0]) > 170 for f in response.json()["features"])


async def test_an_entry_near_a_pole_is_grouped_like_any_other(db_session, make_member, world):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    for _ in range(2):
        await _at(db_session, author, 89.95, 0.0)

    response = await _clusters(guest, 2)

    assert response.status_code == 200, response.text
    assert response.json()["features"][0]["properties"]["count"] == 2


async def test_the_answer_is_capped_and_says_so(db_session, make_member, world, monkeypatch):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    for lat in (10.0, 20.0, 30.0):
        await _at(db_session, author, lat, 10.0)
    monkeypatch.setattr(atlas_service, "CLUSTER_FEATURES_MAX", 2)

    grouped = await _clusters(guest, 8)
    open_ = await _clusters(guest, atlas_service.CLUSTER_OFF_ZOOM)
    fits = await _clusters(guest, 8, west=9, south=9, east=11, north=11)

    assert (len(grouped.json()["features"]), grouped.json()["truncated"]) == (2, True)
    assert (len(open_.json()["features"]), open_.json()["truncated"]) == (2, True)
    assert (len(fits.json()["features"]), fits.json()["truncated"]) == (1, False)


async def test_an_entry_gone_between_the_two_reads_is_left_out(
    db_session, make_member, world, monkeypatch
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    await _at(db_session, author, *EXACT)

    async def nothing(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(atlas_service, "_entries_by_id", nothing)

    assert (await _clusters(guest, 8)).json() == {
        "type": "FeatureCollection",
        "features": [],
        "truncated": False,
    }


async def test_a_bad_window_or_zoom_is_refused(make_member, world):
    guest = await make_member(signed_in=False)
    base = {**WHOLE, "zoom": 5}
    assert (await guest.http.get("/atlas/clusters", params=WHOLE)).status_code == 422
    for bad in ({"zoom": -1}, {"zoom": 23}, {"zoom": "x"}, {"east": 181}, {"north": 91}):
        assert (await guest.http.get("/atlas/clusters", params={**base, **bad})).status_code == 422
    assert (
        await guest.http.get("/atlas/clusters", params={**base, "country": "tun"})
    ).status_code == 422
    assert (
        await guest.http.get("/atlas/clusters", params={**base, "concept": "a b"})
    ).status_code == 422


# ─── The page ───


def _page_params(**extra):
    return {**WHOLE, "center_lat": 36.8, "center_lng": 10.18, **extra}


async def _page(client, **extra):
    return await client.http.get("/atlas/entries/page", params=_page_params(**extra))


async def _seed_by_distance(db, author) -> list[str]:
    """Five entries; the ids come back nearest the centre first, the two nearest tied."""
    far = await _at(db, author, 37.5, 10.2)
    near_a = await _at(db, author, *EXACT)
    mid = await _at(db, author, 37.0, 10.2)
    near_b = await _at(db, author, *EXACT)
    farthest = await _at(db, author, 40.0, 10.2)
    assert near_a != near_b
    return [near_a, near_b, mid, far, farthest]


async def test_the_page_lists_the_nearest_first_with_a_cursor_and_the_total(
    db_session, make_member, world
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    expected = await _seed_by_distance(db_session, author)

    first = await _page(guest, limit=2)
    second = await _page(guest, limit=2, cursor=first.json()["next_cursor"])
    third = await _page(guest, limit=2, cursor=second.json()["next_cursor"])

    assert first.status_code == 200, first.text
    assert first.headers["cache-control"] == "no-store"
    pages = [r.json() for r in (first, second, third)]
    assert [[i["id"] for i in p["items"]] for p in pages] == [
        expected[:2],
        expected[2:4],
        expected[4:],
    ]
    # The tie of the two nearest, and of any two, breaks by id.
    assert int(expected[0]) < int(expected[1])
    assert [p["total"] for p in pages] == [5, 5, 5]
    assert pages[2]["next_cursor"] is None
    assert set(pages[0]) == {"items", "next_cursor", "total"}
    assert pages[0]["items"][0]["properties"]["author"]["handle"] == "author"
    # A distance is used to order and never shown.
    assert "distance" not in keys_of(pages[0]) and "distance" not in first.text
    assert str(EXACT[0]) not in first.text and str(EXACT[1]) not in first.text


async def test_the_pages_neither_skip_nor_repeat_when_an_entry_appears_between_them(
    db_session, make_member, world
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    expected = await _seed_by_distance(db_session, author)
    first = await _page(guest, limit=2)

    newcomer = await _at(db_session, author, 36.8, 10.18)
    rest: list[str] = []
    cursor = first.json()["next_cursor"]
    while cursor is not None:
        page = (await _page(guest, limit=2, cursor=cursor)).json()
        assert page["total"] == 6
        rest += [i["id"] for i in page["items"]]
        cursor = page["next_cursor"]

    seen = [i["id"] for i in first.json()["items"]] + rest
    # Nobody the reader was shown is shown again, and nobody that was there is skipped; the
    # newcomer is listed only if it lies beyond where the reader had got to.
    assert len(seen) == len(set(seen))
    assert set(expected) <= set(seen) <= {*expected, newcomer}


async def test_the_total_follows_the_window_the_filters_and_the_blocks(
    db_session, make_member, world
):
    author = await make_member("author")
    other = await make_member("other")
    reader = await make_member("reader")
    guest = await make_member(signed_in=False)
    await _at(db_session, author, *EXACT, entity_ids=["rain"])
    await _at(db_session, other, 37.0, 10.2, entity_ids=["tree"])
    await _at(db_session, other, -33.9, 151.2, entity_ids=["rain"])

    async def total(client, **extra):
        response = await _page(client, limit=1, **extra)
        assert response.status_code == 200, response.text
        return response.json()["total"]

    assert await total(guest) == 3
    assert await total(guest, **TUNIS_WINDOW) == 2
    assert await total(guest, concept="rain") == 2
    assert await total(guest, country="FR") == 0
    assert await total(guest, since="2999-01-01") == 0
    assert (await _page(guest, since="2999-01-01")).json()["items"] == []
    assert (await reader.http.put("/blocks/other")).status_code == 204
    assert await total(reader) == 1
    assert (await _page(reader)).json()["items"][0]["properties"]["author"]["handle"] == "author"


async def test_the_page_crosses_the_antimeridian(db_session, make_member, world):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    east = await _at(db_session, author, 0.5, 179.9)
    west = await _at(db_session, author, 0.5, -179.9)
    await _at(db_session, author, *EXACT)

    response = await guest.http.get(
        "/atlas/entries/page",
        params={
            "west": 170,
            "south": -10,
            "east": -170,
            "north": 10,
            "center_lat": 0.5,
            "center_lng": 179.95,
        },
    )

    assert {i["id"] for i in response.json()["items"]} == {east, west}
    assert response.json()["total"] == 2


async def test_a_bad_page_request_is_refused(make_member, world):
    guest = await make_member(signed_in=False)
    assert (await guest.http.get("/atlas/entries/page", params=WHOLE)).status_code == 422
    for bad in ({"limit": 0}, {"limit": 51}, {"center_lat": 91}, {"center_lng": -181}):
        assert (await _page(guest, **bad)).status_code == 422
    assert (await _page(guest, cursor="not-a-cursor")).status_code == 400
    # A cursor of another list holds no distance: it is not this one's.
    elsewhere = cursors.encode(cursors.Cursor(at=atlas_service._DISTANCE_CURSOR_AT, id=1))
    assert (await _page(guest, cursor=elsewhere)).json()["error"] == "INVALID_CURSOR"
    # The page still answers on a window with nothing in it.
    empty = await _page(guest)
    assert empty.json() == {"items": [], "next_cursor": None, "total": 0}


async def test_the_new_routes_answer_404_while_the_atlas_is_off(make_member, world, account_app):
    guest = await make_member(signed_in=False)
    settings = account_app.state.settings
    account_app.state.settings = settings.model_copy(update={"disabled_features": "atlas"})
    try:
        for url, params in (
            ("/atlas/clusters", {**WHOLE, "zoom": 3}),
            ("/atlas/entries/page", _page_params()),
        ):
            off = await guest.http.get(url, params=params)
            assert (off.status_code, off.json()["error"]) == (404, "FEATURE_DISABLED")
    finally:
        account_app.state.settings = settings


# ─── What a viewer must not be able to learn or reach ───


async def test_a_centre_is_snapped_before_use_so_that_two_in_one_cell_give_the_same_pages(
    db_session, make_member, world
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    await _seed_by_distance(db_session, author)
    seen: list[str] = []

    def spy(_conn, _cursor, _statement, parameters, *_rest):
        seen.append(str(parameters))

    engine = db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", spy)
    try:
        # Both lie inside the same 0.05 degree cell.
        one = await guest.http.get(
            "/atlas/entries/page",
            params={**WHOLE, "center_lat": 36.8123, "center_lng": 10.1777, "limit": 2},
        )
        other = await guest.http.get(
            "/atlas/entries/page",
            params={**WHOLE, "center_lat": 36.8201, "center_lng": 10.1801, "limit": 2},
        )
        follow = {"cursor": one.json()["next_cursor"], "limit": 2}
        first = await guest.http.get(
            "/atlas/entries/page",
            params={**WHOLE, "center_lat": 36.8123, "center_lng": 10.1777, **follow},
        )
        second = await guest.http.get(
            "/atlas/entries/page",
            params={**WHOLE, "center_lat": 36.8201, "center_lng": 10.1801, **follow},
        )
    finally:
        event.remove(engine, "before_cursor_execute", spy)

    assert one.status_code == other.status_code == 200
    assert one.json() == other.json() and one.json()["next_cursor"] is not None
    assert first.json() == second.json() and first.json()["items"]
    assert seen
    # Neither position reached the database as sent.
    for sent in ("36.8123", "10.1777", "36.8201", "10.1801"):
        assert not any(sent in statement for statement in seen)


async def test_only_what_a_viewer_may_see_is_counted_boxed_and_listed(
    db_session, make_member, world, account_app
):
    """One entry of every hidden kind lies beside two visible ones; none moves a count or the box."""
    for name in ("visiblea", "visibleb"):
        await entry_row(db_session, await make_member(name), age_days=1)
    away = {"lat": 36.9, "lng": 10.4, "age_days": 1}
    for name, status in (
        ("held", MapEntryStatus.PENDING_REVIEW),
        ("removed", MapEntryStatus.REMOVED),
        ("draft", MapEntryStatus.DRAFT),
        ("withdrawn", MapEntryStatus.WITHDRAWN),
        ("orphan", MapEntryStatus.ORPHANED),
    ):
        await entry_row(db_session, await make_member(name), status=status, **away)
    closed = await make_member("closed")
    closed.user.is_active = False
    nameless = await make_member("nameless")
    nameless.user.handle = None
    await entry_row(db_session, closed, **away)
    await entry_row(db_session, nameless, **away)
    sponsored = await entry_row(db_session, await make_member("sponsoredauthor"), **away)
    sponsor = await make_member("sponsor")
    db_session.add(MapEntrySponsorship(entry_id=sponsored.id, user_id=sponsor.user.id))
    await db_session.flush()
    reader = await make_member("reader")
    guest = await make_member(signed_in=False)
    assert (await reader.http.put("/blocks/sponsor")).status_code == 204

    async def seen(client):
        clusters = await _clusters(client, 2)
        page = await _page(client, limit=50)
        return clusters.json()["features"], page.json()

    features, page = await seen(reader)

    assert [f["properties"]["count"] for f in features] == [2]
    assert features[0]["properties"]["bbox"] == [10.1815, 36.8065, 10.1815, 36.8065]
    assert page["total"] == 2 and len(page["items"]) == 2
    # The guest blocks nobody, so the sponsored entry shows for them, and no other hidden one.
    guest_features, guest_page = await seen(guest)
    assert guest_features[0]["properties"]["count"] == 3 and guest_page["total"] == 3
    # With sponsoring off an orphaned entry is served as the plain anonymous one it is.
    settings = account_app.state.settings
    account_app.state.settings = switched(settings, off=[FeatureFlag.ATLAS_SPONSORSHIP])
    try:
        off_features, off_page = await seen(guest)
    finally:
        account_app.state.settings = settings
    assert off_features[0]["properties"]["count"] == 4 and off_page["total"] == 4


async def test_a_statement_running_too_long_is_cut_and_answers_503(db_session, monkeypatch):
    monkeypatch.setattr(atlas_service, "QUERY_TIMEOUT_MS", 50)

    with pytest.raises(AppError) as caught:
        async with atlas_service._bounded(db_session):
            await db_session.execute(text("SELECT pg_sleep(2)"))

    assert (caught.value.code, caught.value.status_code) == (ErrorCode.SERVICE_UNAVAILABLE, 503)


async def test_another_database_error_is_not_taken_for_a_timeout(db_session):
    with pytest.raises(DBAPIError):
        async with atlas_service._bounded(db_session):
            await db_session.execute(text("SELECT no_such_column FROM no_such_table"))
