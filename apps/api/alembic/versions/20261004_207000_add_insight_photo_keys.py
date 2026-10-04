"""add_insight_photo_keys

Revision ID: 20261004_207000
Revises: 20261004_205000
Create Date: 2026-10-04 21:10:00.000000

An insight keeps the random keys of its photo in the photo store: the owner's
private copy, kept at «تمّ» with consent, and the one public copy made while a
publication shows it. The image itself never enters the database.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261004_207000"
down_revision: str | Sequence[str] | None = "20261004_205000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"


def upgrade() -> None:
    op.add_column("insights", sa.Column("photo_key", sa.String(64), nullable=True), schema=SCHEMA)
    op.add_column(
        "insights", sa.Column("photo_public_key", sa.String(64), nullable=True), schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_column("insights", "photo_public_key", schema=SCHEMA)
    op.drop_column("insights", "photo_key", schema=SCHEMA)
