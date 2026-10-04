"""The grid-cell approximation of a location: deterministic, never finer than asked, right at the edges of the map."""

from __future__ import annotations

import math
import random
from itertools import pairwise

import pytest

from src.geo import privacy
from src.geo.privacy import (
    DEFAULT_CELL_METERS,
    MAX_CELL_METERS,
    METERS_PER_DEGREE,
    MIN_CELL_METERS,
    Cell,
    LatLng,
    approximate,
    cell_of,
    cell_polygon,
)

TUNIS = (36.8065, 10.1815)
MECCA = (21.4225, 39.8262)
PLACES = [
    TUNIS,
    MECCA,
    (0.0, 0.0),
    (-0.0001, 0.0001),
    (-33.8688, 151.2093),  # Sydney
    (64.1466, -21.9426),  # Reykjavik
    (69.6492, 18.9553),  # Tromso
    (-0.1807, -78.4678),  # Quito, on the equator
    (-54.8019, -68.303),  # Ushuaia
    (-17.7134, -178.065),  # Fiji, beside the antimeridian
    (51.5, 179.9999),
    (51.5, -179.9999),
]
CELL_SIZES = [MIN_CELL_METERS, 500.0, DEFAULT_CELL_METERS, 5_000.0, MAX_CELL_METERS]


def metres_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance, on the sphere the grid itself assumes."""
    lat1, lng1, lat2, lng2 = map(math.radians, (*a, *b))
    hav = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    )
    return 2 * math.asin(math.sqrt(hav)) * METERS_PER_DEGREE * 180 / math.pi


def signed_area(ring: list[list[float]]) -> float:
    """Shoelace sum in the plane of the positions: positive when the ring runs counter-clockwise."""
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in pairwise(ring)) / 2


@pytest.mark.parametrize("cell_m", CELL_SIZES)
@pytest.mark.parametrize(("lat", "lng"), PLACES)
def test_the_cell_contains_the_point_and_is_at_least_the_requested_size(lat, lng, cell_m):
    cell = cell_of(lat, lng, cell_m)
    slack = 1e-9

    assert cell.south - slack <= lat <= cell.north + slack
    assert cell.west - slack <= lng <= cell.east + slack or lng == 180
    assert -90 <= cell.south < cell.north <= 90
    assert -180 <= cell.west < cell.east <= 180
    height = (cell.north - cell.south) * METERS_PER_DEGREE
    assert cell_m - 1e-6 <= height < cell_m * 1.01
    # At its narrowest edge, the one nearer the pole, a cell is not narrower than asked
    # and is under twice as wide (the polar caps are the one exception, below).
    width = (cell.east - cell.west) * METERS_PER_DEGREE
    width *= math.cos(math.radians(max(abs(cell.south), abs(cell.north))))
    assert cell_m - 1e-6 <= width < 2 * cell_m


@pytest.mark.parametrize("cell_m", CELL_SIZES)
@pytest.mark.parametrize(("lat", "lng"), PLACES)
def test_the_published_point_is_the_centre_of_that_cell_and_close_to_the_real_one(lat, lng, cell_m):
    published = approximate(lat, lng, cell_m)
    cell = cell_of(lat, lng, cell_m)

    assert isinstance(published, LatLng)
    assert published == LatLng(round(cell.centre.lat, 6), round(cell.centre.lng, 6))
    # At most half a diagonal away: the cell is about a square, up to twice as wide as tall.
    assert metres_between((lat, lng), published) <= 1.2 * cell_m


@pytest.mark.parametrize("cell_m", CELL_SIZES)
def test_the_same_question_always_has_the_same_answer_and_the_answer_is_stable(cell_m):
    generator = random.Random(2026)  # noqa: S311 - a fixed sequence of test points, not a secret
    for _ in range(300):
        lat, lng = generator.uniform(-90, 90), generator.uniform(-180, 180)
        first = approximate(lat, lng, cell_m)

        assert {approximate(lat, lng, cell_m) for _ in range(20)} == {first}
        # The published point is itself in the cell it stands for.
        assert approximate(*first, cell_m) == first
        assert cell_of(*first, cell_m) == cell_of(lat, lng, cell_m)


def test_every_point_of_a_cell_gives_one_answer_and_the_next_cell_another():
    cell = cell_of(*TUNIS)
    inside = [
        (cell.south + (cell.north - cell.south) * a, cell.west + (cell.east - cell.west) * b)
        for a in (0.05, 0.5, 0.95)
        for b in (0.05, 0.5, 0.95)
    ]

    assert len({approximate(*point) for point in inside}) == 1
    assert approximate(cell.north + 1e-4, cell.west + 1e-4) != approximate(*inside[0])
    assert approximate(cell.south + 1e-4, cell.east + 1e-4) != approximate(*inside[0])


def test_no_randomness_is_involved_so_averaging_many_queries_reveals_nothing_more():
    answers = {approximate(*MECCA) for _ in range(5_000)}

    assert len(answers) == 1
    # And the one answer is not the real point.
    assert next(iter(answers)) != MECCA


def test_a_bigger_cell_is_taller_and_the_error_stays_inside_it():
    sizes = [500.0, 1_000.0, 5_000.0, 25_000.0]
    heights = [
        (cell_of(*TUNIS, size).north - cell_of(*TUNIS, size).south) * METERS_PER_DEGREE
        for size in sizes
    ]

    assert heights == sorted(heights)
    assert len(set(heights)) == len(sizes)
    assert all(metres_between(TUNIS, approximate(*TUNIS, size)) <= 1.2 * size for size in sizes)


def test_the_default_size_is_a_kilometre():
    assert DEFAULT_CELL_METERS == 1000.0
    assert approximate(*TUNIS) == approximate(*TUNIS, 1000.0)
    assert cell_polygon(*TUNIS) == cell_polygon(*TUNIS, 1000.0)


def test_zero_is_a_coordinate_and_not_a_missing_one():
    published = approximate(0, 0)
    on_the_equator = approximate(0.0, 12.0)
    on_the_meridian = approximate(12.0, 0.0)

    assert isinstance(published, LatLng)
    assert metres_between((0, 0), published) <= 1.2 * DEFAULT_CELL_METERS
    # The equator and the prime meridian are places on the map like any other.
    assert abs(on_the_equator.lat) < 0.01
    assert abs(on_the_meridian.lng) < 0.01
    assert approximate(0, 0) == approximate(0.0, -0.0)


def test_longitude_180_and_minus_180_are_the_same_line_and_the_same_cell():
    assert approximate(51.5, 180) == approximate(51.5, -180)
    assert cell_polygon(51.5, 180) == cell_polygon(51.5, -180)
    assert cell_of(51.5, 180).west == -180


def test_either_side_of_the_antimeridian_are_two_cells_that_meet_at_it():
    west_side = cell_of(51.5, 179.9999)
    east_side = cell_of(51.5, -179.9999)

    assert west_side.east == 180
    assert east_side.west == -180
    assert approximate(51.5, 179.9999) != approximate(51.5, -179.9999)
    assert -180 < approximate(51.5, 179.9999).lng < 180
    assert -180 < approximate(51.5, -179.9999).lng < 180
    # Their published points are about a cell apart, not half the world.
    assert metres_between(approximate(51.5, 179.9999), approximate(51.5, -179.9999)) < 3_000


def test_no_cell_crosses_the_antimeridian_so_no_polygon_does_either():
    generator = random.Random(180)  # noqa: S311 - a fixed sequence of test points, not a secret
    for _ in range(200):
        lat, lng = generator.uniform(-89.9, 89.9), generator.choice([-1, 1]) * generator.random()
        ring = cell_polygon(lat, 180 - lng if lng > 0 else -180 - lng)["coordinates"][0]
        longitudes = [position[0] for position in ring]

        assert -180 <= min(longitudes) < max(longitudes) <= 180


@pytest.mark.parametrize("lat", [90, -90, 89.99999, -89.99999])
@pytest.mark.parametrize("lng", [-180, -90, 0, 90, 180])
def test_the_poles_have_cells_too(lat, lng):
    cell = cell_of(lat, lng)
    published = approximate(lat, lng)

    assert cell.north == 90 if lat > 0 else cell.south == -90
    assert -90 < published.lat < 90
    assert -180 < published.lng < 180
    # The cap is a ring of a kilometre's height around the pole, one cell wide.
    assert metres_between((lat, lng), published) < 1.2 * DEFAULT_CELL_METERS * 2
    assert abs(published.lat) > 89.99


def test_the_cell_polygon_is_closed_counter_clockwise_and_in_longitude_latitude_order():
    polygon = cell_polygon(*TUNIS)
    ring = polygon["coordinates"][0]
    cell = cell_of(*TUNIS)

    assert polygon["type"] == "Polygon"
    assert len(polygon["coordinates"]) == 1
    assert len(ring) == 5
    assert ring[0] == ring[-1]
    assert signed_area(ring) > 0
    # [longitude, latitude]: Tunis is at 10.18 east, 36.8 north.
    assert all(9 < longitude < 11 and 36 < latitude < 38 for longitude, latitude in ring)
    assert ring[0] == [round(cell.west, 6), round(cell.south, 6)]
    assert ring[2] == [round(cell.east, 6), round(cell.north, 6)]
    west, south = ring[0]
    east, north = ring[2]
    assert west <= TUNIS[1] <= east
    assert south <= TUNIS[0] <= north


def test_the_cell_polygon_of_a_point_in_the_western_and_southern_hemisphere_keeps_the_order():
    # A swap would put these longitudes (-70) in the latitude slot, outside -90..90 for others.
    ring = cell_polygon(-54.8019, -68.303)["coordinates"][0]

    assert all(-69 < longitude < -67 and -56 < latitude < -54 for longitude, latitude in ring)


def test_a_cell_knows_its_centre():
    assert Cell(south=10, north=20, west=-30, east=-10).centre == LatLng(15, -20)


@pytest.mark.parametrize(
    ("lat", "lng"),
    [
        (90.0001, 0),
        (-90.0001, 0),
        (0, 180.0001),
        (0, -180.0001),
        (math.nan, 0),
        (0, math.nan),
        (math.inf, 0),
        (0, -math.inf),
    ],
)
def test_a_coordinate_off_the_earth_is_refused(lat, lng):
    with pytest.raises(ValueError, match=r"latitude|longitude"):
        approximate(lat, lng)
    with pytest.raises(ValueError, match=r"latitude|longitude"):
        cell_polygon(lat, lng)


@pytest.mark.parametrize(
    "cell_m", [0, -1000, MIN_CELL_METERS - 1, MAX_CELL_METERS + 1, math.nan, math.inf]
)
def test_a_cell_size_that_hides_nothing_or_everything_is_refused(cell_m):
    with pytest.raises(ValueError, match="cell size"):
        approximate(*TUNIS, cell_m)
    with pytest.raises(ValueError, match="cell size"):
        cell_polygon(*TUNIS, cell_m)


def test_the_limits_are_those_the_settings_use():
    from src.config import Settings

    field = Settings.model_fields["geo_approx_cell_meters"]
    bounds = {type(meta).__name__: meta for meta in field.metadata}

    assert field.default == privacy.DEFAULT_CELL_METERS
    assert bounds["Ge"].ge == privacy.MIN_CELL_METERS
    assert bounds["Le"].le == privacy.MAX_CELL_METERS


def test_the_cell_size_is_read_from_the_environment_and_refused_out_of_range(
    make_settings, monkeypatch
):
    from pydantic import ValidationError

    from src.config import format_validation_error

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1/db")
    monkeypatch.setenv("GEO_APPROX_CELL_METERS", "500")
    assert make_settings().geo_approx_cell_meters == 500.0

    for bad in ("50", "60000", "nan", "wide"):
        monkeypatch.setenv("GEO_APPROX_CELL_METERS", bad)
        with pytest.raises(ValidationError) as caught:
            make_settings()
        assert "GEO_APPROX_CELL_METERS" in format_validation_error(caught.value)
