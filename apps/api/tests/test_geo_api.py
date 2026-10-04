"""The /geo routes over HTTP: validation, headers, and the shape of the answers."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient

from src.database import get_db
from src.main import create_app
from tests import geo_dataset as world_data
from tests.geo_dataset import (
    MECCA,
    MECCA_CITY,
    TUNIS,
    TUNIS_CITY,
    TUNISIA,
    ZERO_POINT,
)
from tests.helpers import client_for


@pytest.fixture
async def geo(db_session, make_settings) -> AsyncIterator[AsyncClient]:
    """A client of an application whose requests are served by the test's own session."""
    await world_data.load_world(db_session)
    application = create_app(make_settings())

    async def use_the_test_session():
        yield db_session

    application.dependency_overrides[get_db] = use_the_test_session
    async with client_for(application) as http:
        yield http


# ─── /geo/search ────────────────────────────────────────────────────


async def test_search_by_an_arabic_name_returns_places_with_arabic_labels(geo):
    response = await geo.get("/geo/search", params={"q": "تونس"})

    assert response.status_code == 200
    hits = response.json()
    assert [hit["geoname_id"] for hit in hits][:2] == [TUNISIA, TUNIS_CITY]
    assert hits[1]["label"] == "تونس"
    assert hits[1]["country"]["iso2"] == "TN"
    assert response.headers["content-type"].startswith("application/json")


async def test_search_by_a_latin_name_and_a_limit(geo):
    response = await geo.get("/geo/search", params={"q": "mecca", "limit": 1})

    assert [hit["geoname_id"] for hit in response.json()] == [MECCA_CITY]


async def test_search_answers_an_empty_list_when_nothing_matches(geo):
    response = await geo.get("/geo/search", params={"q": "zzzzzz"})

    assert response.status_code == 200
    assert response.json() == []


async def test_a_search_is_never_cached_by_a_shared_cache(geo):
    response = await geo.get("/geo/search", params={"q": "Tunis"})

    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"q": ""},
        {"q": "a"},
        {"q": "x" * 101},
        {"q": "ab\x00cd"},
        {"q": "Tunis", "limit": 0},
        {"q": "Tunis", "limit": 51},
        {"q": "Tunis", "limit": "many"},
    ],
)
async def test_search_refuses_a_bad_request_with_the_documented_error_body(geo, params):
    response = await geo.get("/geo/search", params=params)

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "VALIDATION_ERROR"
    assert body["fields"]


# ─── /geo/reverse ───────────────────────────────────────────────────


async def test_reverse_names_the_nearest_place_its_region_and_its_country(geo):
    response = await geo.get("/geo/reverse", params={"lat": TUNIS[0], "lng": TUNIS[1]})

    assert response.status_code == 200
    body = response.json()
    assert body["place"]["geoname_id"] == TUNIS_CITY
    assert body["place"]["label"] == "تونس"
    assert body["admin_area"]["label"] == "ولاية تونس"
    assert body["country"]["label"] == "تونس"
    assert body["place"]["distance_m"] == pytest.approx(1970, abs=100)


async def test_reverse_gives_longitude_first_in_the_geojson_and_both_plainly(geo):
    response = await geo.get("/geo/reverse", params={"lat": MECCA[0], "lng": MECCA[1]})

    place = response.json()["place"]
    assert place["geoname_id"] == MECCA_CITY
    # Mecca is at 39.8 east, 21.4 north: a swapped pair would put 39.8 in latitude.
    assert place["location"] == {"type": "Point", "coordinates": [39.82563, 21.42664]}
    assert (place["latitude"], place["longitude"]) == (21.42664, 39.82563)


async def test_reverse_accepts_a_coordinate_of_zero(geo):
    response = await geo.get("/geo/reverse", params={"lat": 0, "lng": 0})

    assert response.status_code == 200
    assert response.json()["place"]["geoname_id"] == ZERO_POINT
    # Only one of the two being zero is as valid.
    assert (await geo.get("/geo/reverse", params={"lat": 0, "lng": 10.5})).status_code == 200
    assert (await geo.get("/geo/reverse", params={"lat": 36.8, "lng": 0})).status_code == 200


@pytest.mark.parametrize(
    ("lat", "lng"), [(90, 180), (-90, -180), (90, -180), (-90, 180), (89.999, 179.999)]
)
async def test_reverse_accepts_the_corners_of_the_map(geo, lat, lng):
    response = await geo.get("/geo/reverse", params={"lat": lat, "lng": lng})

    assert response.status_code == 200
    assert response.json() == {"place": None, "admin_area": None, "country": None}


async def test_reverse_takes_a_radius(geo):
    near = await geo.get(
        "/geo/reverse", params={"lat": TUNIS[0], "lng": TUNIS[1], "radius_m": 1000}
    )
    wide = await geo.get(
        "/geo/reverse", params={"lat": TUNIS[0], "lng": TUNIS[1], "radius_m": 5000}
    )

    assert near.json()["place"] is None
    assert wide.json()["place"]["geoname_id"] == TUNIS_CITY


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"lat": 1},
        {"lng": 1},
        {"lat": 90.0001, "lng": 0},
        {"lat": -90.0001, "lng": 0},
        {"lat": 0, "lng": 180.0001},
        {"lat": 0, "lng": -180.0001},
        {"lat": "north", "lng": 0},
        {"lat": "nan", "lng": 0},
        {"lat": 0, "lng": "inf"},
        {"lat": "", "lng": 0},
        {"lat": 0, "lng": 0, "radius_m": 99},
        {"lat": 0, "lng": 0, "radius_m": 100_001},
    ],
)
async def test_reverse_refuses_a_point_off_the_earth(geo, params):
    response = await geo.get("/geo/reverse", params=params)

    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"


async def test_reverse_neither_echoes_the_point_nor_lets_it_be_cached(geo):
    response = await geo.get("/geo/reverse", params={"lat": 36.80123, "lng": 10.18123})

    assert response.headers["cache-control"] == "no-store"
    assert "36.80123" not in response.text
    assert "10.18123" not in response.text


# ─── /geo/countries ─────────────────────────────────────────────────


async def test_countries_lists_every_country_and_may_be_cached(geo):
    response = await geo.get("/geo/countries")

    assert response.status_code == 200
    assert [country["iso2"] for country in response.json()] == ["FR", "SA", "TN"]
    assert response.json()[2]["label"] == "تونس"
    assert response.headers["cache-control"] == "public, max-age=86400"


# ─── The contract ───────────────────────────────────────────────────


async def test_the_routes_are_in_the_published_contract_with_longitude_first_documented(geo):
    spec = (await geo.get("/openapi.json")).json()

    assert {"/geo/search", "/geo/reverse", "/geo/countries"} <= set(spec["paths"])
    assert spec["paths"]["/geo/reverse"]["get"]["tags"] == ["geo"]
    point = spec["components"]["schemas"]["GeoJsonPoint"]["properties"]["coordinates"]
    assert point["description"] == "[longitude, latitude]"
