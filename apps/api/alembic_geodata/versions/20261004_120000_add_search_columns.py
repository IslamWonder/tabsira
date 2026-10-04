"""add_search_columns

Revision ID: 20261004_120000
Revises: 20261004_090000
Create Date: 2026-10-04 12:00:00.000000

What place search and the reverse lookup need on top of the GeoNames tables:

- `geodata.normalize_name`, the one way a name is folded for searching;
- `geonames.ar_name`, the preferred Arabic name of a place;
- `geonames_alternate_names.name_norm`, the folded name, with a trigram index
  for fuzzy matches and a prefix index;
- a geography index on the place points, so ST_DWithin in metres uses an index;
- a partial index on the ADM1 rows, to find a place's region;
- a unique (parent, child) pair on the hierarchy, which the monthly update
  upserts on.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261004_120000"
down_revision: str | Sequence[str] | None = "20261004_090000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "geodata"

# A copy of the function in src/models/geonames.py, frozen here: a later change
# to the folding is a new migration, never an edit of this one. A test compares
# the two while they are meant to be the same.
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


def upgrade() -> None:
    op.execute(NORMALIZE_NAME_SQL)

    op.add_column("geonames", sa.Column("ar_name", sa.Text(), nullable=True), schema=SCHEMA)

    op.add_column(
        "geonames_alternate_names",
        sa.Column(
            "name_norm",
            sa.Text(),
            sa.Computed("geodata.normalize_name(alternate_name)", persisted=True),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_geonames_alternate_names_name_norm_trgm",
        "geonames_alternate_names",
        ["name_norm"],
        schema=SCHEMA,
        postgresql_using="gin",
        postgresql_ops={"name_norm": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_geonames_alternate_names_name_norm_prefix",
        "geonames_alternate_names",
        ["name_norm"],
        schema=SCHEMA,
        postgresql_ops={"name_norm": "text_pattern_ops"},
    )

    op.create_index(
        "ix_geonames_location_geog",
        "geonames",
        [sa.text("geography(location_geom)")],
        schema=SCHEMA,
        postgresql_using="gist",
    )
    op.create_index(
        "ix_geonames_adm1",
        "geonames",
        ["country_code", "admin1_code"],
        schema=SCHEMA,
        postgresql_where=sa.text("feature_code = 'ADM1'"),
    )

    op.create_unique_constraint(
        "uq_geonames_hierarchy_parent_child",
        "geonames_hierarchy",
        ["parent_id", "child_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_geonames_hierarchy_parent_child", "geonames_hierarchy", schema=SCHEMA, type_="unique"
    )
    op.drop_index("ix_geonames_adm1", table_name="geonames", schema=SCHEMA)
    op.drop_index("ix_geonames_location_geog", table_name="geonames", schema=SCHEMA)
    op.drop_index(
        "ix_geonames_alternate_names_name_norm_prefix",
        table_name="geonames_alternate_names",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_geonames_alternate_names_name_norm_trgm",
        table_name="geonames_alternate_names",
        schema=SCHEMA,
    )
    op.drop_column("geonames_alternate_names", "name_norm", schema=SCHEMA)
    op.drop_column("geonames", "ar_name", schema=SCHEMA)
    op.execute("DROP FUNCTION IF EXISTS geodata.normalize_name(text)")
