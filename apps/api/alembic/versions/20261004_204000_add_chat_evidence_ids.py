"""add_chat_evidence_ids

Revision ID: 20261004_204000
Revises: 20261004_203000
Create Date: 2026-10-04 20:40:00.000000

A chat answer keeps the evidence ids shown when it was written. Answers
written before are left null: they are never shown or sent to the model again.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261004_204000"
down_revision: str | Sequence[str] | None = "20261004_203000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"


def upgrade() -> None:
    op.add_column(
        "insight_chat_messages",
        sa.Column("evidence_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("insight_chat_messages", "evidence_ids", schema=SCHEMA)
