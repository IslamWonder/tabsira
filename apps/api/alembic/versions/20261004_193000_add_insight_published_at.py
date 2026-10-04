"""add_insight_published_at

Revision ID: 20261004_193000
Revises: 20261004_192500
Create Date: 2026-10-04 19:30:00.000000

An insight its owner made public (v2 §18): `insights.published_at` is the
moment it was published, null while it is private or after it was withdrawn.
The partial index lists the public ones for the sitemap, oldest first.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261004_193000"
down_revision: str | Sequence[str] | None = "20261004_192500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"


def upgrade() -> None:
    op.add_column(
        "insights",
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_insights_public",
        "insights",
        ["id"],
        unique=False,
        schema=SCHEMA,
        postgresql_where=sa.text("published_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_insights_public", table_name="insights", schema=SCHEMA)
    op.drop_column("insights", "published_at", schema=SCHEMA)
