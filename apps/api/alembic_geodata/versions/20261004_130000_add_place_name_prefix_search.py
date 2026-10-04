"""add_place_name_prefix_search

Revision ID: 20261004_130000
Revises: 20261004_120000
Create Date: 2026-10-04 13:00:00.000000

The folded GeoNames name of every place, with a prefix index, so that a search
by the beginning of a name reads the places with that beginning in index order
and stops at the most populated, instead of reading every place a trigram scan
turns up. On the full dump (5.8 million places) that is the difference between
a few milliseconds and seconds for a prefix such as "san".
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261004_130000"
down_revision: str | Sequence[str] | None = "20261004_120000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "geodata"


def upgrade() -> None:
    op.add_column(
        "geonames",
        sa.Column(
            "name_norm",
            sa.Text(),
            sa.Computed("geodata.normalize_name(name)", persisted=True),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_geonames_name_norm_prefix",
        "geonames",
        ["name_norm"],
        schema=SCHEMA,
        postgresql_ops={"name_norm": "text_pattern_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_geonames_name_norm_prefix", table_name="geonames", schema=SCHEMA)
    op.drop_column("geonames", "name_norm", schema=SCHEMA)
