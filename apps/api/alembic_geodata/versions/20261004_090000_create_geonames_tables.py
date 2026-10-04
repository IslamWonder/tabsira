"""create_geonames_tables

Revision ID: 20261004_090000
Revises:
Create Date: 2026-10-04 09:00:00.000000

The GeoNames reference tables: places, their alternate names, the hierarchy,
postal codes and country information. The tables are empty here; the import
script fills them.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from geoalchemy2 import Geometry

from alembic import op

revision: str = "20261004_090000"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "geodata"


def upgrade() -> None:
    # This chain runs before the app chain, which creates every extension the
    # product uses. These two are what this migration itself needs: postgis for
    # the geometry column, pg_trgm for the name index. IF NOT EXISTS makes the
    # app chain's later CREATE a no-op; a missing extension fails here, loudly.
    # In schema public, whatever the role's search_path says.
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public")
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "geonames",
        sa.Column("geoname_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("latitude", sa.Float(precision=53), nullable=True),
        sa.Column("longitude", sa.Float(precision=53), nullable=True),
        sa.Column("feature_class", sa.Text(), nullable=True),
        sa.Column("feature_code", sa.Text(), nullable=True),
        sa.Column("country_code", sa.Text(), nullable=True),
        sa.Column("cc2", sa.Text(), nullable=True),
        sa.Column("admin1_code", sa.Text(), nullable=True),
        sa.Column("admin2_code", sa.Text(), nullable=True),
        sa.Column("admin3_code", sa.Text(), nullable=True),
        sa.Column("admin4_code", sa.Text(), nullable=True),
        sa.Column("population", sa.BigInteger(), nullable=True),
        sa.Column("timezone", sa.Text(), nullable=True),
        sa.Column("modification_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "location_geom", Geometry("POINT", srid=4326, spatial_index=False), nullable=True
        ),
        sa.PrimaryKeyConstraint("geoname_id", name="pk_geonames"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_geonames_country_admin1", "geonames", ["country_code", "admin1_code"], schema=SCHEMA
    )
    op.create_index("ix_geonames_feature_class", "geonames", ["feature_class"], schema=SCHEMA)
    op.create_index("ix_geonames_feature_code", "geonames", ["feature_code"], schema=SCHEMA)
    op.create_index("ix_geonames_is_active", "geonames", ["is_active"], schema=SCHEMA)
    op.create_index("ix_geonames_population", "geonames", ["population"], schema=SCHEMA)
    op.create_index(
        "ix_geonames_modification_date", "geonames", ["modification_date"], schema=SCHEMA
    )
    # Fuzzy place-name search.
    op.create_index(
        "ix_geonames_name_trgm",
        "geonames",
        ["name"],
        schema=SCHEMA,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    # Nearest-place and bounding-box queries.
    op.create_index(
        "ix_geonames_location_geom",
        "geonames",
        ["location_geom"],
        schema=SCHEMA,
        postgresql_using="gist",
    )

    op.create_table(
        "geonames_alternate_names",
        sa.Column("alternate_name_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("geoname_id", sa.Integer(), nullable=False),
        sa.Column("iso_language", sa.Text(), nullable=True),
        sa.Column("alternate_name", sa.Text(), nullable=False),
        sa.Column("is_preferred", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_short", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_colloquial", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_historic", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.PrimaryKeyConstraint("alternate_name_id", name="pk_geonames_alternate_names"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_geonames_alternate_names_geoname_id",
        "geonames_alternate_names",
        ["geoname_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_geonames_alternate_names_language",
        "geonames_alternate_names",
        ["iso_language"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_geonames_alternate_names_name",
        "geonames_alternate_names",
        ["alternate_name"],
        schema=SCHEMA,
    )

    op.create_table(
        "geonames_hierarchy",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=False),
        sa.Column("child_id", sa.Integer(), nullable=False),
        sa.Column("hierarchy_type", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_geonames_hierarchy"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_geonames_hierarchy_parent_id", "geonames_hierarchy", ["parent_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_geonames_hierarchy_child_id", "geonames_hierarchy", ["child_id"], schema=SCHEMA
    )

    op.create_table(
        "geonames_postal_codes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("country_code", sa.Text(), nullable=True),
        sa.Column("postal_code", sa.Text(), nullable=True),
        sa.Column("place_name", sa.Text(), nullable=True),
        sa.Column("admin_name1", sa.Text(), nullable=True),
        sa.Column("admin_code1", sa.Text(), nullable=True),
        sa.Column("admin_name2", sa.Text(), nullable=True),
        sa.Column("admin_code2", sa.Text(), nullable=True),
        sa.Column("admin_name3", sa.Text(), nullable=True),
        sa.Column("admin_code3", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Float(precision=53), nullable=True),
        sa.Column("longitude", sa.Float(precision=53), nullable=True),
        sa.Column("accuracy", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_geonames_postal_codes"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_geonames_postal_codes_country", "geonames_postal_codes", ["country_code"], schema=SCHEMA
    )
    op.create_index(
        "ix_geonames_postal_codes_code", "geonames_postal_codes", ["postal_code"], schema=SCHEMA
    )
    op.create_index(
        "ix_geonames_postal_codes_place", "geonames_postal_codes", ["place_name"], schema=SCHEMA
    )
    op.create_index(
        "ix_geonames_postal_codes_admin1",
        "geonames_postal_codes",
        ["country_code", "admin_code1"],
        schema=SCHEMA,
    )

    op.create_table(
        "geonames_country_info",
        sa.Column("iso2", sa.Text(), nullable=False),
        sa.Column("iso3", sa.Text(), nullable=True),
        sa.Column("iso_numeric", sa.Integer(), nullable=True),
        sa.Column("fips", sa.Text(), nullable=True),
        sa.Column("country_name", sa.Text(), nullable=False),
        sa.Column("capital", sa.Text(), nullable=True),
        sa.Column("area_km2", sa.Float(precision=53), nullable=True),
        sa.Column("population", sa.BigInteger(), nullable=True),
        sa.Column("continent", sa.Text(), nullable=True),
        sa.Column("top_level_domain", sa.Text(), nullable=True),
        sa.Column("currency_code", sa.Text(), nullable=True),
        sa.Column("currency_name", sa.Text(), nullable=True),
        sa.Column("phone_prefix", sa.Text(), nullable=True),
        sa.Column("postal_code_format", sa.Text(), nullable=True),
        sa.Column("languages", sa.Text(), nullable=True),
        sa.Column("geoname_id", sa.Integer(), nullable=True),
        sa.Column("neighbours", sa.Text(), nullable=True),
        sa.Column("flag_emoji", sa.Text(), nullable=True),
        sa.Column("equivalent_fips", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("iso2", name="pk_geonames_country_info"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_geonames_country_info_iso3", "geonames_country_info", ["iso3"], schema=SCHEMA
    )
    op.create_index(
        "ix_geonames_country_info_continent", "geonames_country_info", ["continent"], schema=SCHEMA
    )


def downgrade() -> None:
    # Dropping a table drops its indexes. The schema stays: it also holds this
    # chain's alembic_version table.
    for table in (
        "geonames_country_info",
        "geonames_postal_codes",
        "geonames_hierarchy",
        "geonames_alternate_names",
        "geonames",
    ):
        op.drop_table(table, schema=SCHEMA)
