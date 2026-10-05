from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import pytest

from mockdata import places
from mockdata.places import COUNTRIES, City, Gazetteer, Place


class FakeResult:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


class FakeConn:
    """Answers the two queries; records every statement so tests can prove it only reads."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, query: str, params: Any = None) -> FakeResult:
        self.statements.append(query)
        if "feature_class = 'P'" in query:
            return FakeResult(
                [
                    (1, "Tunis", "تونس", 36.8, 10.18, "TN", 600000),
                    (2, "Nowhere", "لا مكان", 0.0, 0.0, "EG", 20000),
                ]
            )
        assert params is not None
        west, south, east, north = params
        rows = [
            (10, 36.80, 10.18),  # at the centre
            (11, 36.85, 10.20),  # inside the box and the radius
            (12, 36.87, 10.27),  # inside the box, beyond the radius
        ]
        if south < 1:
            return FakeResult([])
        return FakeResult([r for r in rows if south <= r[1] <= north and west <= r[2] <= east])


def test_gazetteer_reads_cities_and_places_near_each() -> None:
    conn = FakeConn()
    gazetteer = places.fetch_gazetteer(conn)
    assert [c.geoname_id for c in gazetteer.cities] == [1, 2]
    assert [p.geoname_id for p in gazetteer.places[1]] == [10, 11]
    # A city with no feature nearby is its own place.
    assert gazetteer.places[2] == (Place(2, 0.0, 0.0),)
    assert all(s.lstrip().upper().startswith("SELECT") for s in conn.statements)


def test_cache_round_trip(tmp_path: Path) -> None:
    gazetteer = places.fetch_gazetteer(FakeConn())
    path = tmp_path / "x" / "cache.json"
    places.save(path, gazetteer)
    assert places.load(path) == gazetteer


def test_haversine_known_distance() -> None:
    assert places.haversine_km(0, 0, 0, 1) == pytest.approx(111.19, abs=0.1)
    assert places.haversine_km(10, 10, 10, 10) == 0


def test_quotas_sum_to_total_with_a_floor() -> None:
    quotas = places.country_quotas(1000)
    assert sum(quotas.values()) == 1000
    assert set(quotas) == set(COUNTRIES)
    assert min(quotas.values()) >= places.MIN_PER_COUNTRY
    assert quotas["EG"] > quotas["TN"] > quotas["KM"]


def test_quotas_refuse_a_total_below_the_floor() -> None:
    with pytest.raises(ValueError, match="at least 220"):
        places.country_quotas(100)


def test_pick_city_is_weighted_by_population() -> None:
    cities = [City(1, "a", "x", 0, 0, "TN", 1), City(2, "b", "y", 0, 0, "TN", 1_000_000)]
    rng = random.Random(1)
    picks = [places.pick_city(rng, cities).geoname_id for _ in range(200)]
    assert picks.count(2) > 190


@pytest.mark.parametrize("lat", [0.0, 36.8, 70.0])
def test_points_stay_within_the_distance_of_their_place(lat: float) -> None:
    rng = random.Random(3)
    place = Place(1, lat, 10.0)
    for _ in range(300):
        lng_, lat_ = places.draw_point(rng, place)  # GeoJSON order
        assert (
            places.haversine_km(place.latitude, place.longitude, lat_, lng_)
            <= places.POINT_RADIUS_KM
        )


def test_point_is_longitude_first() -> None:
    lng, lat = places.draw_point(random.Random(0), Place(1, 36.8, 10.18))
    assert abs(lng - 10.18) < 0.1
    assert abs(lat - 36.8) < 0.1


def test_gazetteer_type_is_frozen(gazetteer: Gazetteer) -> None:
    assert len(gazetteer.cities) == len(COUNTRIES)
