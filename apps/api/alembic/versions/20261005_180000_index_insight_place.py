"""index_insight_place

Revision ID: 20261005_180000
Revises: 20261005_120000
Create Date: 2026-10-05 16:30:00.000000

The insights table had no index on `place_id`, unlike its sibling
`treasures.place_id`: the world read each place's completed insights with a
sequential scan, and deleting a world place had to find the insights that
point at it (ON DELETE SET NULL) the same way, on the largest per-owner
table.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261005_180000"
down_revision: str | Sequence[str] | None = "20261005_120000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"


def upgrade() -> None:
    op.create_index(
        "ix_insights_place_id",
        "insights",
        ["place_id"],
        unique=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_insights_place_id", table_name="insights", schema=SCHEMA)
