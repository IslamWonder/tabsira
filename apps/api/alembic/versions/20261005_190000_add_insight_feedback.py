"""add_insight_feedback

Revision ID: 20261005_190000
Revises: 20261005_180000
Create Date: 2026-10-05 19:00:00.000000

The owner's own rating of an insight: useful or not, the reasons of a «not useful»
chosen from a list, and an optional note of 300 characters. One row per insight,
deleted with it; the admin reads the open ones and marks them reviewed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261005_190000"
down_revision: str | Sequence[str] | None = "20261005_180000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"


def upgrade() -> None:
    op.create_table(
        "insight_feedback",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("insight_id", sa.BigInteger(), nullable=False),
        sa.Column("helpful", sa.Boolean(), nullable=False),
        sa.Column("reasons", postgresql.ARRAY(sa.String(32)), nullable=False),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "note IS NULL OR char_length(note) <= 300", name=op.f("ck_insight_feedback_note_length")
        ),
        sa.CheckConstraint(
            "NOT helpful OR cardinality(reasons) = 0",
            name=op.f("ck_insight_feedback_reasons_when_not_helpful"),
        ),
        sa.CheckConstraint("state IN ('open', 'reviewed')", name=op.f("ck_insight_feedback_state")),
        sa.ForeignKeyConstraint(
            ["insight_id"],
            ["app.insights.id"],
            name=op.f("fk_insight_feedback_insight_id_insights"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_insight_feedback")),
        sa.UniqueConstraint("insight_id", name="uq_insight_feedback_insight_id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_insight_feedback_state_updated_at",
        "insight_feedback",
        ["state", "updated_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_insight_feedback_state_updated_at", "insight_feedback", schema=SCHEMA)
    op.drop_table("insight_feedback", schema=SCHEMA)
