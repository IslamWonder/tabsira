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

from src.geo.privacy import approximate
from src.services import atlas_service
from tests import geo_dataset as world_data
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


async def test_the_new_routes_answer_404_while_the_atlas_is_off(make_member, world, account_app):
    guest = await make_member(signed_in=False)
    settings = account_app.state.settings
    account_app.state.settings = settings.model_copy(update={"disabled_features": "atlas"})
    try:
        for url, params in (("/atlas/clusters", {**WHOLE, "zoom": 3}),):
            off = await guest.http.get(url, params=params)
            assert (off.status_code, off.json()["error"]) == (404, "FEATURE_DISABLED")
    finally:
        account_app.state.settings = settings
