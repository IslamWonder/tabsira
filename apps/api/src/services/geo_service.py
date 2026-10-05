"""
Place search, reverse lookup and countries, over the GeoNames tables of the `geodata` schema.

Nothing here leaves our database: no geocoder is called (DECISIONS.md, decision 9).

Search folds the query the way the stored names are folded (the database
function `geodata.normalize_name`: case, accents, Arabic vowel marks, alef,
ta marbuta and ya variants), then looks for it in the Arabic and English
alternate names and in the GeoNames name: exact matches first, then names that
start with it, each by population, then, if there are too few, names that are
only similar to it, by similarity.

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
# Shorter queries are matched by prefix only: a trigram match on three letters
# is every name that has them somewhere.
FUZZY_MIN_LENGTH = 4
# Above every character, so that `name < prefix + this` holds for every name that starts with prefix.
_AFTER_EVERY_CHARACTER = "\U0010ffff"

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

# The search runs in tiers, each cheaper to run than the next and stronger as a match:
#   0  the folded name equals the folded query, in an Arabic or English alternate
#      name or in the GeoNames name;
#   1  a folded name starts with the query. The GeoNames names are read in index
#      order and cut at the most populated 100 places, which is all the final
#      ranking can use, so a short common prefix costs milliseconds where a scan
#      of a table of millions of places would cost seconds;
#   2  a name is similar to the query (trigram). Only when tiers 0 and 1 gave fewer
#      than :limit places, and when the query is long enough (:fuzzy): it is the
#      fallback for a misspelling, and the costly one.
# A prefix is a range, `>= :n AND < :n_hi`, in the operators of the text_pattern_ops
# indexes, not a LIKE: the range works whatever way the statement is planned, and
# a `%` or `_` typed by the user is just a character.
_SEARCH = (
    """
WITH by_name AS MATERIALIZED (
    SELECT a.geoname_id, 0 AS tier
    FROM geodata.geonames_alternate_names a
    WHERE a.iso_language IN ('ar', 'en') AND a.name_norm = :n
  UNION ALL
    SELECT g.geoname_id, 0
    FROM geodata.geonames g
    WHERE g.is_active AND g.name_norm = :n
  UNION ALL
    SELECT a.geoname_id, 1
    FROM geodata.geonames_alternate_names a
    WHERE a.iso_language IN ('ar', 'en') AND a.name_norm ~>=~ :n AND a.name_norm ~<~ :n_hi
  UNION ALL
    (SELECT g.geoname_id, 1
     FROM geodata.geonames g
     WHERE g.is_active AND g.name_norm ~>=~ :n AND g.name_norm ~<~ :n_hi
     ORDER BY g.population DESC NULLS LAST
     LIMIT 100)
), sure AS MATERIALIZED (
    SELECT h.geoname_id, min(h.tier) AS tier, 0::real AS sim
    FROM by_name h
    JOIN geodata.geonames g USING (geoname_id)
    WHERE g.is_active AND g.feature_class IN ('P', 'A')
      AND g.latitude IS NOT NULL AND g.longitude IS NOT NULL
    GROUP BY h.geoname_id
), fuzzy AS (
    SELECT geoname_id, 2 AS tier, sim
    FROM (
        (SELECT a.geoname_id, similarity(a.name_norm, :n) AS sim
         FROM geodata.geonames_alternate_names a
         WHERE a.iso_language IN ('ar', 'en') AND a.name_norm % :n
         ORDER BY sim DESC
         LIMIT 100)
      UNION ALL
        (SELECT g.geoname_id, similarity(g.name_norm, :n) AS sim
         FROM geodata.geonames g
         WHERE g.is_active AND g.name % :raw
         ORDER BY sim DESC
         LIMIT 100)
    ) AS candidates
    WHERE CAST(:fuzzy AS boolean) AND (SELECT count(*) FROM sure) < :limit
), best AS (
    SELECT geoname_id, min(tier) AS tier, max(sim) AS sim
    FROM (SELECT * FROM sure UNION ALL SELECT * FROM fuzzy) AS everything
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
        "location": GeoJsonPoint(coordinates=[row["longitude"], row["latitude"]]),
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
    # The database folds the query, with the function that folded the names.
    folded = (
        await db.execute(text("SELECT geodata.normalize_name(:q)"), {"q": query})
    ).scalar_one()
    if not folded:
        return []
    params = {
        "n": folded,
        "n_hi": folded + _AFTER_EVERY_CHARACTER,
        "raw": query.strip(),
        "fuzzy": len(folded) >= FUZZY_MIN_LENGTH,
        "limit": limit,
    }
    rows = (await db.execute(text(_SEARCH), params)).mappings().all()
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


# The Arabic label of every country, by ISO2 code, read once per process: GeoNames changes a few
# times a year, with a reinstall that restarts the API. Empty until the first read, and an empty
# answer is not kept, so a database that had no geodata yet is asked again.
_country_labels: dict[str, str] = {}


async def country_labels(db: AsyncSession) -> dict[str, str]:
    """Return the label of every GeoNames country by ISO2 code, the way `/geo/countries` shows it."""
    if not _country_labels:
        rows = (await db.execute(text(_COUNTRIES))).mappings().all()
        _country_labels.update(
            {row["iso2"]: _label(row["country_name"], row["ar_name"]) for row in rows}
        )
    return _country_labels


def forget_country_labels() -> None:
    """Empty the in-process copy, so the next read asks the database again (tests, a reinstall)."""
    _country_labels.clear()
