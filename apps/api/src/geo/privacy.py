"""
Location privacy: a point is published as the centre of the grid cell it falls in.

The exact point of a photo never reaches a public API (AGENTS.md; extension
section 10). What is published instead is computed here, on the server, from a
grid that is fixed once and for all by the cell size.

Why a grid cell and not random jitter. A random offset drawn on every request
can be averaged: a reader who asks n times gets n noisy points whose mean
approaches the true one, the error shrinking as 1/sqrt(n). A random offset
drawn once and stored survives that, but it is one more secret to keep and a
second source (a neighbouring entry, a distance filter) can be subtracted from
it. A grid cell has neither weakness: every point of the cell, and every
request for it, gives the same answer, so asking again reveals nothing new, and
the answer is the same whoever asks. Distances and filters must be computed
from the published point and never from the private one, or they would leak
what the rounding hid.

Shape of the grid. Rows are bands of equal latitude. Each row is cut into equal
columns of longitude, as many as fit its width in metres, so a cell stays about
as wide as it is tall at every latitude instead of becoming a sliver towards
the poles. The rows tile latitude -90..90 exactly and the columns of each row
tile longitude -180..180 exactly, so no cell ever straddles the antimeridian:
the meridians 180 and -180 are one line and belong to the same column. A cell
is never smaller than the requested size in either direction (its narrowest
edge, the one nearer the pole, is at least `cell_m` wide) and is under twice
that wide; rounding down the number of rows and columns errs on the private side.

This is a rounding to a region, not a guarantee: a cell in a thinly populated
area can still point at one house. The owner reviews the published point and
may coarsen it or withdraw it.

GeoJSON order is [longitude, latitude]. `approximate` returns a `LatLng`, named
fields in the order of its arguments, so the two orders are not mixed up by
accident.
"""

from __future__ import annotations

import math
from typing import Any, NamedTuple

# Metres in one degree of latitude on a sphere of the mean Earth radius (6371008.8 m).
METERS_PER_DEGREE = 111_194.93

DEFAULT_CELL_METERS = 1000.0
# Finer than this hides nothing worth hiding; coarser makes the label useless.
MIN_CELL_METERS = 100.0
MAX_CELL_METERS = 50_000.0

# Coordinates of a published point are kept to about a tenth of a metre.
_DECIMALS = 6


class LatLng(NamedTuple):
    """A position, latitude first as in the arguments of every function here."""

    lat: float
    lng: float


class Cell(NamedTuple):
    """The edges of a grid cell, in degrees."""

    south: float
    north: float
    west: float
    east: float

    @property
    def centre(self) -> LatLng:
        return LatLng((self.south + self.north) / 2, (self.west + self.east) / 2)


def _check(lat: float, lng: float, cell_m: float) -> None:
    """Refuse anything that is not a coordinate on Earth or a usable cell size."""
    if not math.isfinite(lat) or not -90 <= lat <= 90:
        message = "latitude must be a number from -90 to 90"
        raise ValueError(message)
    if not math.isfinite(lng) or not -180 <= lng <= 180:
        message = "longitude must be a number from -180 to 180"
        raise ValueError(message)
    if not math.isfinite(cell_m) or not MIN_CELL_METERS <= cell_m <= MAX_CELL_METERS:
        message = f"cell size must be from {MIN_CELL_METERS:g} to {MAX_CELL_METERS:g} metres"
        raise ValueError(message)


def cell_of(lat: float, lng: float, cell_m: float = DEFAULT_CELL_METERS) -> Cell:
    """Return the grid cell that contains the point, for cells of about `cell_m` metres."""
    _check(lat, lng, cell_m)

    rows = max(1, math.floor(180 * METERS_PER_DEGREE / cell_m))
    lat_step = 180 / rows
    # The pole belongs to the last row, not to a row that does not exist.
    row = min(int((lat + 90) // lat_step), rows - 1)
    south = -90 + row * lat_step
    north = 90 if row == rows - 1 else south + lat_step

    # Columns are counted at the edge of the row nearest the pole, where it is narrowest.
    narrowest = 360 * METERS_PER_DEGREE * math.cos(math.radians(max(abs(south), abs(north))))
    columns = max(1, math.floor(narrowest / cell_m))
    lng_step = 360 / columns
    # 180 and -180 are the same meridian: both belong to the first column.
    column = int(((-180.0 if lng == 180 else lng) + 180) // lng_step) % columns
    west = -180 + column * lng_step
    east = 180 if column == columns - 1 else west + lng_step

    return Cell(south, north, west, east)


def approximate(lat: float, lng: float, cell_m: float = DEFAULT_CELL_METERS) -> LatLng:
    """
    Return the centre of the grid cell that contains the point.

    Deterministic: for one cell size every point of a cell gives the same
    answer, on every call, so asking again reveals nothing. Raises ValueError
    for a coordinate outside the Earth or a cell size outside the allowed
    range. Zero is a coordinate like any other.
    """
    centre = cell_of(lat, lng, cell_m).centre
    return LatLng(round(centre.lat, _DECIMALS), round(centre.lng, _DECIMALS))


def cell_polygon(lat: float, lng: float, cell_m: float = DEFAULT_CELL_METERS) -> dict[str, Any]:
    """
    Return the grid cell that contains the point as a GeoJSON Polygon.

    The ring is closed and counter-clockwise (RFC 7946) and every position is
    [longitude, latitude]. This is the shape to publish for an approximate
    location: a region, not a point that pretends to be where the photo was taken.
    """
    cell = cell_of(lat, lng, cell_m)
    south, north = round(cell.south, _DECIMALS), round(cell.north, _DECIMALS)
    west, east = round(cell.west, _DECIMALS), round(cell.east, _DECIMALS)
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "Polygon", "coordinates": [ring]}
