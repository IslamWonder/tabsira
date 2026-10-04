from __future__ import annotations

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from src.models import (
    Base,
    GeoAlternateName,
    GeoBase,
    GeoCountryInfo,
    GeoHierarchy,
    GeoName,
    GeoPostalCode,
)
from src.models.base import NAMING_CONVENTION


def test_each_base_has_its_own_schema_and_the_shared_naming_convention():
    assert Base.metadata.schema == "app"
    assert GeoBase.metadata.schema == "geodata"
    assert Base.metadata.naming_convention == NAMING_CONVENTION
    assert GeoBase.metadata.naming_convention == NAMING_CONVENTION


def test_geonames_tables_live_in_the_geodata_schema_only():
    expected = {
        "geodata.geonames",
        "geodata.geonames_alternate_names",
        "geodata.geonames_hierarchy",
        "geodata.geonames_postal_codes",
        "geodata.geonames_country_info",
    }

    assert set(GeoBase.metadata.tables) == expected
    assert not {name for name in Base.metadata.tables if name.startswith("geodata.")}
    assert {
        m.__table__.fullname
        for m in (GeoName, GeoAlternateName, GeoHierarchy, GeoPostalCode, GeoCountryInfo)
    } == expected


def test_geonames_carries_a_trigram_and_a_gist_index():
    indexes = {index.name: index for index in GeoName.__table__.indexes}
    dialect = postgresql.dialect()

    assert "USING gin (name gin_trgm_ops)" in str(
        CreateIndex(indexes["ix_geonames_name_trgm"]).compile(dialect=dialect)
    )
    assert "USING gist (location_geom)" in str(
        CreateIndex(indexes["ix_geonames_location_geom"]).compile(dialect=dialect)
    )


def test_primary_keys_follow_the_naming_convention():
    ddl = str(CreateTable(GeoCountryInfo.__table__).compile(dialect=postgresql.dialect()))

    assert "CONSTRAINT pk_geonames_country_info PRIMARY KEY (iso2)" in ddl
