"""add_profile_questions_asked

Revision ID: 20261004_205000
Revises: 20261004_204000
Create Date: 2026-10-04 20:50:00.000000

The optional questions (master prompt v2 §5) are offered once, after the first
insight; answered or skipped, the profile remembers that they were asked so a
returning person is never asked again (§4.9). Existing profiles start as not
asked, like a new one.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261004_205000"
down_revision: str | Sequence[str] | None = "20261004_204000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"


def upgrade() -> None:
    op.add_column(
        "profiles",
        sa.Column("questions_asked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("profiles", "questions_asked", schema=SCHEMA)
