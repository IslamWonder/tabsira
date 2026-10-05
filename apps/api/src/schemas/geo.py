"""
Bodies of the geo routes: places found by name, the place nearest a point, countries.

Everything here comes from the GeoNames tables in our own database; nothing is
sent to a geocoder. A place has its GeoNames name and, when GeoNames knows one,
its Arabic name; `label` is the one to show: the Arabic name when there is one.
Positions are given twice, as plain `latitude` and `longitude` and as a GeoJSON
Point, whose coordinates are [longitude, latitude].
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class GeoJsonPoint(BaseModel):
    """A GeoJSON Point (RFC 7946): `coordinates` is [longitude, latitude]."""

    type: Literal["Point"] = "Point"
    coordinates: Annotated[list[float], Field(min_length=2, max_length=2)] = Field(
        description="[longitude, latitude]"
    )


class AdminArea(BaseModel):
    """The first-level administrative division (region, governorate, state) of a place."""

    geoname_id: int
    name: str
    name_ar: str | None
    label: str


class CountryRef(BaseModel):
    """The country of a place."""

    iso2: str
    name: str
    name_ar: str | None
    label: str


class Place(BaseModel):
    """A named place: a populated place or an administrative division."""

    geoname_id: int
    name: str
    name_ar: str | None
    label: str
    feature_class: str | None
    feature_code: str | None
    population: int | None
    latitude: float
    longitude: float
    location: GeoJsonPoint


class PlaceHit(Place):
    """A place that matched a search, with its region and country to tell namesakes apart."""

    admin_area: AdminArea | None
    country: CountryRef | None


class NearbyPlace(Place):
    """The populated place nearest to a point."""

    distance_m: int = Field(description="Metres from the point, on the ellipsoid")


class ReverseResult(BaseModel):
    """What is near a point. Every field is null when no populated place is in range."""

    place: NearbyPlace | None
    admin_area: AdminArea | None
    country: CountryRef | None


class Country(BaseModel):
    """A country, from the GeoNames country information."""

    iso2: str
    iso3: str | None
    name: str
    name_ar: str | None
    label: str
    capital: str | None
    continent: str | None
    flag_emoji: str | None
    population: int | None


class PublicCountryOut(BaseModel):
    """A declared country shown by consent (decision 67): public profile and post author only."""

    code: str = Field(description="ISO 3166-1 alpha-2")
    name: str = Field(description="Its Arabic name from GeoNames, the label of /geo/countries")
