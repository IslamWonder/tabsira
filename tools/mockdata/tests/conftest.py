from __future__ import annotations

from datetime import datetime

import pytest

from mockdata.catalogue import KEEP_CATEGORIES, Photo
from mockdata.places import COUNTRIES, City, Gazetteer, Place

NOW = datetime(2026, 10, 5, 10, 0, 0)


@pytest.fixture
def gazetteer() -> Gazetteer:
    """One city per country, 100 000 people each, with a few places near it (invented numbers)."""
    cities: list[City] = []
    places: dict[int, tuple[Place, ...]] = {}
    for n, code in enumerate(sorted(COUNTRIES)):
        gid = 1000 + n
        lat, lng = 10.0 + n, 20.0 + n
        cities.append(City(gid, f"City{n}", f"مدينة{n}", lat, lng, code, 100_000 + n))
        places[gid] = tuple(
            Place(gid * 10 + k, lat + k * 0.01, lng - k * 0.01) for k in range(1, 4)
        )
    return Gazetteer(tuple(cities), places)


@pytest.fixture
def photos() -> list[Photo]:
    cats = sorted(KEEP_CATEGORIES)
    return [Photo(i, f"cat-photo-{i}.jpg", cats[i % len(cats)], 800, 600) for i in range(1, 61)]
