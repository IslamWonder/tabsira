"""
Place search, reverse lookup and countries, over the GeoNames tables of the `geodata` schema.

Nothing here leaves our database: no geocoder is called (DECISIONS.md, decision 9).

Search folds the query the way the stored names are folded (the database
function `geodata.normalize_name`: case, accents, Arabic vowel marks, alef,
ta marbuta and ya variants), then looks for it in the Arabic and English
alternate names and in the GeoNames name, by prefix and by trigram similarity.
Exact matches come first, then prefix matches, each by population, then the
fuzzy ones by similarity.

Reverse lookup finds the nearest populated place within a radius with
ST_DWithin on geography, in metres, which the geography index serves.

Coordinates are [longitude, latitude] in GeoJSON and latitude, longitude in
every argument list here. Zero is a coordinate.
"""

# S608 reads a string joined to another as a query built from input. These are
# two constants joined to a third; every value reaches a query as a bind parameter.
# ruff: noqa: S608

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from src.schemas.geo import (
    AdminArea,
    Country,
    CountryRef,
    GeoJsonPoint,
    NearbyPlace,
    PlaceHit,
    ReverseResult,
)

DEFAULT_SEARCH_LIMIT = 10
DEFAULT_RADIUS_M = 25_000.0

# Feature codes of populated places that are not where a person is now: sections
# of a populated place (a neighbourhood), and abandoned, destroyed and historical
# places. The nearest *settlement* is what labels a location.
NOT_A_SETTLEMENT = ("PPLX", "PPLQ", "PPLW", "PPLH", "PPLCH")

# What a place needs to be shown: its region (ADM1 with the same country and
# first-level code) and its country, each with its Arabic name when there is one.
# Appended to a query that ends in a `found` table with a `rank` column.
_WITH_CONTEXT = """
SELECT t.geoname_id, t.name, t.ar_name, t.feature_class, t.feature_code, t.population,
       t.latitude, t.longitude, t.distance_m,
       adm.geoname_id AS admin_id, adm.name AS admin_name, adm.ar_name AS admin_name_ar,
       ci.iso2 AS country_iso2, ci.country_name AS country_name,
       cg.ar_name AS country_name_ar
FROM found t
LEFT JOIN LATERAL (
    SELECT a.geoname_id, a.name, a.ar_name
    FROM geodata.geonames a
    WHERE a.country_code = t.country_code
      AND a.admin1_code = t.admin1_code
      AND a.feature_code = 'ADM1'
      AND a.is_active
      AND a.geoname_id <> t.geoname_id
    ORDER BY a.population DESC NULLS LAST, a.geoname_id
    LIMIT 1
) adm ON true
LEFT JOIN geodata.geonames_country_info ci ON ci.iso2 = t.country_code
LEFT JOIN geodata.geonames cg ON cg.geoname_id = ci.geoname_id AND cg.is_active
ORDER BY t.rank
"""

# `!` is the LIKE escape, so that a `%` or `_` typed by the user matches itself.
_SEARCH = (
    """
WITH typed AS (
    SELECT geodata.normalize_name(:q) AS n, btrim(:q) AS raw
), pat AS (
    SELECT n, raw,
           replace(replace(replace(n, '!', '!!'), '%', '!%'), '_', '!_') || '%' AS n_prefix,
           replace(replace(replace(raw, '!', '!!'), '%', '!%'), '_', '!_') || '%' AS raw_prefix
    FROM typed
), hits AS (
    SELECT a.geoname_id,
           CASE WHEN a.name_norm = pat.n THEN 0
                WHEN a.name_norm LIKE pat.n_prefix ESCAPE '!' THEN 1
                ELSE 2 END AS tier,
           similarity(a.name_norm, pat.n) AS sim
    FROM geodata.geonames_alternate_names a CROSS JOIN pat
    WHERE pat.n <> ''
      AND a.iso_language IN ('ar', 'en')
      AND (a.name_norm LIKE pat.n_prefix ESCAPE '!' OR a.name_norm % pat.n)
  UNION ALL
    SELECT g.geoname_id,
           CASE WHEN geodata.normalize_name(g.name) = pat.n THEN 0
                WHEN geodata.normalize_name(g.name) LIKE pat.n_prefix ESCAPE '!' THEN 1
                ELSE 2 END,
           similarity(geodata.normalize_name(g.name), pat.n)
    FROM geodata.geonames g CROSS JOIN pat
    WHERE pat.n <> ''
      AND g.is_active
      AND (g.name ILIKE pat.raw_prefix ESCAPE '!' OR g.name % pat.raw)
), best AS (
    SELECT geoname_id, min(tier) AS tier, max(sim) AS sim
    FROM hits
    GROUP BY geoname_id
), found AS (
    SELECT g.*, NULL::float8 AS distance_m,
           row_number() OVER (
               ORDER BY best.tier,
                        CASE WHEN best.tier = 2 THEN best.sim END DESC NULLS LAST,
                        g.population DESC NULLS LAST,
                        g.geoname_id
           ) AS rank
    FROM best
    JOIN geodata.geonames g USING (geoname_id)
    WHERE g.is_active
      AND g.feature_class IN ('P', 'A')
      AND g.latitude IS NOT NULL
      AND g.longitude IS NOT NULL
    ORDER BY rank
    LIMIT :limit
)
"""
    + _WITH_CONTEXT
)

_REVERSE = (
    """
WITH here AS (
    SELECT ST_SetSRID(
               ST_MakePoint(CAST(:lng AS float8), CAST(:lat AS float8)), 4326
           )::geography AS point
), found AS (
    SELECT g.*, ST_Distance(g.location_geom::geography, here.point) AS distance_m,
           1 AS rank
    FROM geodata.geonames g CROSS JOIN here
    WHERE g.is_active
      AND g.feature_class = 'P'
      AND NOT (g.feature_code = ANY(CAST(:excluded AS text[])))
      AND ST_DWithin(g.location_geom::geography, here.point, CAST(:radius_m AS float8))
    ORDER BY distance_m, g.population DESC NULLS LAST, g.geoname_id
    LIMIT 1
)
"""
    + _WITH_CONTEXT
)

_COUNTRIES = """
SELECT ci.iso2, ci.iso3, ci.country_name, cg.ar_name, ci.capital, ci.continent,
       ci.flag_emoji, ci.population
FROM geodata.geonames_country_info ci
LEFT JOIN geodata.geonames cg ON cg.geoname_id = ci.geoname_id AND cg.is_active
ORDER BY ci.country_name, ci.iso2
"""


def _label(name: str, name_ar: str | None) -> str:
    """Return the name to show: the Arabic one when GeoNames has it."""
    return name_ar or name


def _place_fields(row: RowMapping) -> dict[str, Any]:
    """Return the columns of one place as the fields of a `Place`."""
    return {
        "geoname_id": row["geoname_id"],
        "name": row["name"],
        "name_ar": row["ar_name"],
        "label": _label(row["name"], row["ar_name"]),
        "feature_class": row["feature_class"],
        "feature_code": row["feature_code"],
        "population": row["population"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        # GeoJSON order: longitude first.
        "location": GeoJsonPoint(coordinates=(row["longitude"], row["latitude"])),
    }


def _admin_area(row: RowMapping) -> AdminArea | None:
    if row["admin_id"] is None:
        return None
    return AdminArea(
        geoname_id=row["admin_id"],
        name=row["admin_name"],
        name_ar=row["admin_name_ar"],
        label=_label(row["admin_name"], row["admin_name_ar"]),
    )


def _country(row: RowMapping) -> CountryRef | None:
    if row["country_iso2"] is None:
        return None
    return CountryRef(
        iso2=row["country_iso2"],
        name=row["country_name"],
        name_ar=row["country_name_ar"],
        label=_label(row["country_name"], row["country_name_ar"]),
    )


async def search_places(
    db: AsyncSession, query: str, limit: int = DEFAULT_SEARCH_LIMIT
) -> list[PlaceHit]:
    """
    Return the places whose Arabic, English or GeoNames name matches `query`.

    A query that folds to nothing (only punctuation) matches nothing.
    """
    rows = (await db.execute(text(_SEARCH), {"q": query, "limit": limit})).mappings().all()
    return [
        PlaceHit(**_place_fields(row), admin_area=_admin_area(row), country=_country(row))
        for row in rows
    ]


async def nearest_place(
    db: AsyncSession, lat: float, lng: float, radius_m: float = DEFAULT_RADIUS_M
) -> ReverseResult:
    """
    Return the populated place nearest to the point within `radius_m` metres, with its region and country.

    Neighbourhoods and abandoned or historical places are not candidates. The
    answer holds nothing about the point itself, only about the place found.
    """
    params = {
        "lat": lat,
        "lng": lng,
        "radius_m": radius_m,
        "excluded": list(NOT_A_SETTLEMENT),
    }
    row = (await db.execute(text(_REVERSE), params)).mappings().first()
    if row is None:
        return ReverseResult(place=None, admin_area=None, country=None)
    return ReverseResult(
        place=NearbyPlace(**_place_fields(row), distance_m=round(row["distance_m"])),
        admin_area=_admin_area(row),
        country=_country(row),
    )


async def list_countries(db: AsyncSession) -> list[Country]:
    """Return every country, by English name, with the Arabic name where GeoNames has one."""
    rows = (await db.execute(text(_COUNTRIES))).mappings().all()
    return [
        Country(
            iso2=row["iso2"],
            iso3=row["iso3"],
            name=row["country_name"],
            name_ar=row["ar_name"],
            label=_label(row["country_name"], row["ar_name"]),
            capital=row["capital"],
            continent=row["continent"],
            flag_emoji=row["flag_emoji"],
            population=row["population"],
        )
        for row in rows
    ]
