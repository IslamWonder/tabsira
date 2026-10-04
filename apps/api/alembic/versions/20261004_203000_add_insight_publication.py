"""add_insight_publication

Revision ID: 20261004_201000
Revises: 20261004_200000
Create Date: 2026-10-04 20:10:00.000000

An insight becomes public only by its owner's act: `insights.published_at` is set while it is
public and cleared when it is withdrawn (`withdrawn_at` keeps the last time). A guest's insight
is never public.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261004_203000"
down_revision: str | Sequence[str] | None = "20261004_201000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"


def upgrade() -> None:
    op.add_column("insights", sa.Column("published_at", sa.DateTime(timezone=True)), schema=SCHEMA)
    op.add_column("insights", sa.Column("withdrawn_at", sa.DateTime(timezone=True)), schema=SCHEMA)
    op.create_check_constraint(
        op.f("ck_insights_public_has_account"),
        "insights",
        "published_at IS NULL OR user_id IS NOT NULL",
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_insights_published_at"),
        "insights",
        ["published_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("published_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_insights_published_at"), table_name="insights", schema=SCHEMA)
    op.drop_constraint(
        op.f("ck_insights_public_has_account"), "insights", schema=SCHEMA, type_="check"
    )
    op.drop_column("insights", "withdrawn_at", schema=SCHEMA)
    op.drop_column("insights", "published_at", schema=SCHEMA)
