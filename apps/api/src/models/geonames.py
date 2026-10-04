"""GeoNames reference tables (schema `geodata`), imported once and read-only afterwards."""

from __future__ import annotations

from datetime import date
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    DDL,
    BigInteger,
    Boolean,
    Computed,
    Date,
    Float,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    event,
    false,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.models.geo_base import GeoBase

# One definition of how a place name is folded for searching, kept in the
# database so that the stored names, the query text and the seed scripts all
# fold the same way. Lower case; Latin accents and Arabic vowel marks, the
# elongation stroke and the hamza carriers removed; alef wasla, ta marbuta and
# alef maqsura written as alef, ha and ya (the spellings people type
# interchangeably); hyphens, dots, commas and apostrophes read as spaces.
# IMMUTABLE so that it can back a generated column and an index. The migration
# that created it holds its own copy; a test keeps the two identical.
NORMALIZE_NAME_FUNCTION = "geodata.normalize_name"
NORMALIZE_NAME_SQL = r"""
CREATE OR REPLACE FUNCTION geodata.normalize_name(value text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT AS $fn$
  SELECT btrim(regexp_replace(
    translate(
      regexp_replace(
        normalize(lower(value), NFD),
        '[\u0300-\u036f\u0640\u064b-\u065f\u0670]', '', 'g'),
      E'\u0671\u0629\u0649', E'\u0627\u0647\u064a'),
    '[\s\-.,''\u2018\u2019]+', ' ', 'g'))
$fn$
"""


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
        # A place finds its administrative area by (country, admin1 code); the
        # partial index holds only the few thousand ADM1 rows, so the lookup
        # never scans the places that share the code.
        Index(
            "ix_geonames_adm1",
            "country_code",
            "admin1_code",
            postgresql_where=text("feature_code = 'ADM1'"),
        ),
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
    # The preferred Arabic name, chosen from the Arabic alternate names by the
    # import scripts: the label shown to the user when there is one.
    ar_name: Mapped[str | None] = mapped_column(Text, nullable=True)

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
        # Search by the folded name: fuzzy (trigram) and by prefix.
        Index(
            "ix_geonames_alternate_names_name_norm_trgm",
            "name_norm",
            postgresql_using="gin",
            postgresql_ops={"name_norm": "gin_trgm_ops"},
        ),
        Index(
            "ix_geonames_alternate_names_name_norm_prefix",
            "name_norm",
            postgresql_ops={"name_norm": "text_pattern_ops"},
        ),
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
    # The name as `geodata.normalize_name` folds it. Computed by the database
    # on every write, so it can never disagree with `alternate_name`. Written
    # without the schema, as PostgreSQL reports it back, so that Alembic's
    # comparison finds no difference; the schema is on every connection's
    # search_path (see src/database.py).
    name_norm: Mapped[str] = mapped_column(
        Text, Computed("normalize_name(alternate_name)", persisted=True)
    )


class GeoHierarchy(GeoBase):
    """Parent-child hierarchy from GeoNames hierarchy.txt."""

    __tablename__ = "geonames_hierarchy"
    __table_args__ = (
        Index("ix_geonames_hierarchy_parent_id", "parent_id"),
        Index("ix_geonames_hierarchy_child_id", "child_id"),
        # One row per pair: the monthly reconciliation upserts on it.
        UniqueConstraint("parent_id", "child_id", name="uq_geonames_hierarchy_parent_child"),
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


# The geography view of a place, for distances in metres. An expression index
# on it is what lets ST_DWithin on geography find the places around a point
# without reading every row. Plain `geography(...)`, the same expression the
# queries write as `location_geom::geography`, so the planner matches them.
Index(
    "ix_geonames_location_geog",
    func.geography(GeoName.location_geom),
    postgresql_using="gist",
)

# `create_all` (the test database, a fresh development one) creates the folding
# function before the tables that use it, as the migration does.
event.listen(
    GeoBase.metadata,
    "before_create",
    DDL(NORMALIZE_NAME_SQL),  # type: ignore[no-untyped-call]
)
event.listen(
    GeoBase.metadata,
    "after_drop",
    DDL(f"DROP FUNCTION IF EXISTS {NORMALIZE_NAME_FUNCTION}(text)"),  # type: ignore[no-untyped-call]
)
