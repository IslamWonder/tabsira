"""GeoNames reference tables (schema `geodata`), imported once and read-only afterwards."""

from __future__ import annotations

from datetime import date
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    Float,
    Index,
    Integer,
    Text,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.models.geo_base import GeoBase


class GeoName(GeoBase):
    """GeoNames main table: one row per named place."""

    __tablename__ = "geonames"
    __table_args__ = (
        Index("ix_geonames_country_admin1", "country_code", "admin1_code"),
        Index("ix_geonames_feature_class", "feature_class"),
        Index("ix_geonames_feature_code", "feature_code"),
        Index("ix_geonames_is_active", "is_active"),
        Index("ix_geonames_population", "population"),
        Index("ix_geonames_modification_date", "modification_date"),
        Index(
            "ix_geonames_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index("ix_geonames_location_geom", "location_geom", postgresql_using="gist"),
    )

    # Assigned by GeoNames, never by this database: no sequence behind it.
    geoname_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float(precision=53), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float(precision=53), nullable=True)
    feature_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    feature_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    country_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    cc2: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin1_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin2_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin3_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin4_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    population: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    timezone: Mapped[str | None] = mapped_column(Text, nullable=True)
    modification_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Soft-delete flag (GeoNames monthly reconciliation uses this, never hard-delete)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    # PostGIS geometry
    location_geom: Mapped[Any | None] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False), nullable=True
    )


class GeoAlternateName(GeoBase):
    """Translated / alternate names for GeoName entries (all locales)."""

    __tablename__ = "geonames_alternate_names"
    __table_args__ = (
        Index("ix_geonames_alternate_names_geoname_id", "geoname_id"),
        Index("ix_geonames_alternate_names_language", "iso_language"),
        Index("ix_geonames_alternate_names_name", "alternate_name"),
    )

    alternate_name_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    geoname_id: Mapped[int] = mapped_column(Integer, nullable=False)
    iso_language: Mapped[str | None] = mapped_column(Text, nullable=True)
    alternate_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_preferred: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    is_short: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    is_colloquial: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    is_historic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )


class GeoHierarchy(GeoBase):
    """Parent-child hierarchy from GeoNames hierarchy.txt."""

    __tablename__ = "geonames_hierarchy"
    __table_args__ = (
        Index("ix_geonames_hierarchy_parent_id", "parent_id"),
        Index("ix_geonames_hierarchy_child_id", "child_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[int] = mapped_column(Integer, nullable=False)
    child_id: Mapped[int] = mapped_column(Integer, nullable=False)
    hierarchy_type: Mapped[str | None] = mapped_column(Text, nullable=True)


class GeoPostalCode(GeoBase):
    """Postal codes from the GeoNames postal code dataset."""

    __tablename__ = "geonames_postal_codes"
    __table_args__ = (
        Index("ix_geonames_postal_codes_country", "country_code"),
        Index("ix_geonames_postal_codes_code", "postal_code"),
        Index("ix_geonames_postal_codes_place", "place_name"),
        Index("ix_geonames_postal_codes_admin1", "country_code", "admin_code1"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    place_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_name1: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_code1: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_name2: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_code2: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_name3: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_code3: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float(precision=53), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float(precision=53), nullable=True)
    accuracy: Mapped[int | None] = mapped_column(Integer, nullable=True)


class GeoCountryInfo(GeoBase):
    """Country-level metadata from the GeoNames countryInfo file."""

    __tablename__ = "geonames_country_info"
    __table_args__ = (
        Index("ix_geonames_country_info_iso3", "iso3"),
        Index("ix_geonames_country_info_continent", "continent"),
    )

    iso2: Mapped[str] = mapped_column(Text, primary_key=True)
    iso3: Mapped[str | None] = mapped_column(Text, nullable=True)
    iso_numeric: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fips: Mapped[str | None] = mapped_column(Text, nullable=True)
    country_name: Mapped[str] = mapped_column(Text, nullable=False)
    capital: Mapped[str | None] = mapped_column(Text, nullable=True)
    area_km2: Mapped[float | None] = mapped_column(Float(precision=53), nullable=True)
    population: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    continent: Mapped[str | None] = mapped_column(Text, nullable=True)
    top_level_domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_prefix: Mapped[str | None] = mapped_column(Text, nullable=True)
    postal_code_format: Mapped[str | None] = mapped_column(Text, nullable=True)
    languages: Mapped[str | None] = mapped_column(Text, nullable=True)
    geoname_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    neighbours: Mapped[str | None] = mapped_column(Text, nullable=True)
    flag_emoji: Mapped[str | None] = mapped_column(Text, nullable=True)
    equivalent_fips: Mapped[str | None] = mapped_column(Text, nullable=True)
