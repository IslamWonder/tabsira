"""add_map_entry_photo_flag

Revision ID: 20261004_208000
Revises: 20261004_207000
Create Date: 2026-10-04 21:20:00.000000

A map entry records whether its owner chose to show the insight's photo with it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261004_208000"
down_revision: str | Sequence[str] | None = "20261004_207000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"


def upgrade() -> None:
    op.add_column(
        "map_entries",
        sa.Column("with_photo", sa.Boolean(), server_default=sa.false(), nullable=False),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("map_entries", "with_photo", schema=SCHEMA)
