"""Countries, cities and the real places points are drawn near (GeoNames, read only)."""

from __future__ import annotations

import json
import math
import random
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

EARTH_RADIUS_KM = 6371.0088
POINT_RADIUS_KM = 1.5
# Points are drawn closer than the limit so rounding never crosses it.
DRAW_RADIUS_KM = 1.0
CITY_RADIUS_KM = 8.0
PLACES_PER_CITY = 80
MIN_POPULATION = 15000

# Country: (population in millions, rounded, only a weight) and the Faker locales to try, in order.
COUNTRIES: dict[str, tuple[float, tuple[str, ...]]] = {
    "MA": (37.0, ("ar_AA", "ar_PS")),
    "DZ": (45.0, ("ar_AA", "ar_PS")),
    "TN": (12.0, ("ar_AA", "ar_PS")),
    "LY": (7.0, ("ar_AA", "ar_EG", "ar_PS")),
    "EG": (112.0, ("ar_EG", "ar_PS", "ar_SA")),
    "SD": (48.0, ("ar_EG", "ar_SA", "ar_PS")),
    "MR": (4.9, ("ar_AA", "ar_SA")),
    "SA": (36.0, ("ar_SA",)),
    "AE": (10.0, ("ar_SA", "ar_PS")),
    "QA": (2.9, ("ar_SA",)),
    "KW": (4.3, ("ar_SA",)),
    "BH": (1.5, ("ar_SA",)),
    "OM": (4.6, ("ar_SA",)),
    "YE": (34.0, ("ar_SA", "ar_AA")),
    "JO": (11.0, ("ar_JO", "ar_PS", "ar_SA")),
    "PS": (5.4, ("ar_PS",)),
    "SY": (23.0, ("ar_JO", "ar_PS")),
    "LB": (5.5, ("ar_JO", "ar_PS")),
    "IQ": (45.0, ("ar_SA", "ar_PS")),
    "SO": (18.0, ("ar_AA", "ar_SA")),
    "DJ": (1.1, ("ar_AA", "ar_SA")),
    "KM": (0.9, ("ar_AA", "ar_SA")),
}
MIN_PER_COUNTRY = 10


@dataclass(frozen=True)
class City:
    geoname_id: int
    name: str
    ar_name: str
    latitude: float
    longitude: float
    country: str
    population: int


@dataclass(frozen=True)
class Place:
    geoname_id: int
    latitude: float
    longitude: float


@dataclass(frozen=True)
class Gazetteer:
    cities: tuple[City, ...]
    places: dict[int, tuple[Place, ...]]  # by city geoname id


class Connection(Protocol):
    """What the generator needs from a database connection (psycopg's `execute`)."""

    def execute(self, query: str, params: Sequence[Any] | None = None) -> Any: ...


CITY_SQL = """
SELECT geoname_id, name, ar_name, latitude, longitude, country_code, population
FROM geodata.geonames
WHERE feature_class = 'P' AND population >= %s AND ar_name IS NOT NULL AND ar_name <> ''
  AND latitude IS NOT NULL AND longitude IS NOT NULL AND country_code = ANY(%s)
ORDER BY geoname_id
"""

PLACE_SQL = """
SELECT geoname_id, latitude, longitude
FROM geodata.geonames
WHERE feature_class IN ('S', 'L', 'P') AND latitude IS NOT NULL AND longitude IS NOT NULL
  AND location_geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
ORDER BY population DESC NULLS LAST, geoname_id
"""


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _box(city: City, km: float) -> tuple[float, float, float, float]:
    dlat = km / 111.0
    dlng = km / (111.0 * max(math.cos(math.radians(city.latitude)), 0.01))
    return (
        city.longitude - dlng,
        city.latitude - dlat,
        city.longitude + dlng,
        city.latitude + dlat,
    )


def fetch_gazetteer(conn: Connection) -> Gazetteer:
    """Read the cities of the plan's countries and the places around each. Never writes."""
    rows = conn.execute(CITY_SQL, (MIN_POPULATION, sorted(COUNTRIES))).fetchall()
    cities = tuple(City(int(r[0]), r[1], r[2], r[3], r[4], r[5], int(r[6])) for r in rows)
    places: dict[int, tuple[Place, ...]] = {}
    for city in cities:
        found = conn.execute(PLACE_SQL, _box(city, CITY_RADIUS_KM)).fetchall()
        near = [
            Place(int(r[0]), r[1], r[2])
            for r in found
            if haversine_km(city.latitude, city.longitude, r[1], r[2]) <= CITY_RADIUS_KM
        ]
        places[city.geoname_id] = tuple(near[:PLACES_PER_CITY]) or (
            Place(city.geoname_id, city.latitude, city.longitude),
        )
    return Gazetteer(cities, places)


def save(path: Path, gazetteer: Gazetteer) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "cities": [asdict(c) for c in gazetteer.cities],
        "places": {str(k): [asdict(p) for p in v] for k, v in gazetteer.places.items()},
    }
    path.write_text(json.dumps(data, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def load(path: Path) -> Gazetteer:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Gazetteer(
        tuple(City(**c) for c in data["cities"]),
        {int(k): tuple(Place(**p) for p in v) for k, v in data["places"].items()},
    )


def country_quotas(total: int) -> dict[str, int]:
    """Members per country: square root of the population, at least ten each, summing to total."""
    codes = sorted(COUNTRIES)
    floor = MIN_PER_COUNTRY * len(codes)
    if total < floor:
        message = f"at least {floor} members are needed for {len(codes)} countries"
        raise ValueError(message)
    weights = {c: math.sqrt(COUNTRIES[c][0]) for c in codes}
    spare = total - floor
    scale = spare / sum(weights.values())
    exact = {c: weights[c] * scale for c in codes}
    quotas = {c: MIN_PER_COUNTRY + math.floor(exact[c]) for c in codes}
    left = total - sum(quotas.values())
    for code in sorted(codes, key=lambda c: (-(exact[c] - math.floor(exact[c])), c))[:left]:
        quotas[code] += 1
    return quotas


def pick_city(rng: random.Random, cities: Sequence[City]) -> City:
    return rng.choices(cities, weights=[c.population for c in cities])[0]


def draw_point(rng: random.Random, place: Place) -> tuple[float, float]:
    """A point within DRAW_RADIUS_KM of a real place, as GeoJSON [longitude, latitude]."""
    distance = DRAW_RADIUS_KM * math.sqrt(rng.random())
    bearing = rng.random() * 2 * math.pi
    dlat = distance * math.cos(bearing) / 111.0
    dlng = (
        distance * math.sin(bearing) / (111.0 * max(math.cos(math.radians(place.latitude)), 0.01))
    )
    return (round(place.longitude + dlng, 6), round(place.latitude + dlat, 6))
