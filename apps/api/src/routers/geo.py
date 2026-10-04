"""Place search, reverse lookup and countries, served from the GeoNames tables of our own database."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.schemas.geo import Country, PlaceHit, ReverseResult
from src.services import geo_service

router = APIRouter(prefix="/geo", tags=["geo"])

# What a visitor typed or where they are is theirs: shared caches must not keep it.
NO_STORE = "no-store"
# The country list changes with a GeoNames release, a few times a year.
COUNTRIES_CACHE = "public, max-age=86400"

Latitude = Annotated[float, Query(ge=-90, le=90, description="Degrees, -90 to 90; 0 is valid")]
Longitude = Annotated[float, Query(ge=-180, le=180, description="Degrees, -180 to 180; 0 is valid")]


@router.get("/search", summary="Search places by Arabic or Latin name")
async def search(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    q: Annotated[
        str,
        # PostgreSQL text cannot hold a NUL; refused here, not as a server error later.
        Query(
            min_length=2, max_length=100, pattern=r"^[^\x00]*$", description="Part of a place name"
        ),
    ],
    limit: Annotated[int, Query(ge=1, le=50)] = geo_service.DEFAULT_SEARCH_LIMIT,
) -> list[PlaceHit]:
    """
    Return places whose name matches `q`, in Arabic or in Latin letters.

    Exact matches come first, then names that start with `q`, each by
    population, then similar names. `label` is the Arabic name when there is
    one. The text is matched without regard to case, accents, Arabic vowel
    marks or the alef, ta marbuta and ya variants.
    """
    response.headers["Cache-Control"] = NO_STORE
    return await geo_service.search_places(db, q, limit)


@router.get("/reverse", summary="The populated place nearest to a point")
async def reverse(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    lat: Latitude,
    lng: Longitude,
    radius_m: Annotated[
        float, Query(ge=100, le=100_000, description="Search radius in metres")
    ] = geo_service.DEFAULT_RADIUS_M,
) -> ReverseResult:
    """
    Return the nearest populated place within `radius_m`, with its region and country.

    It labels an approximate location: send the rounded point (see
    `src/geo/privacy.py`), never the exact one of a photo, and keep the answer
    to the place found. Nothing is returned when no populated place is in range.
    """
    response.headers["Cache-Control"] = NO_STORE
    return await geo_service.nearest_place(db, lat, lng, radius_m)


@router.get("/countries", summary="Countries")
async def countries(
    response: Response, db: Annotated[AsyncSession, Depends(get_db)]
) -> list[Country]:
    """Return every country, with its Arabic name when GeoNames has one."""
    response.headers["Cache-Control"] = COUNTRIES_CACHE
    return await geo_service.list_countries(db)
