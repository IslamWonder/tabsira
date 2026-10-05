"""widen_insight_photo_key

Revision ID: 20261005_150000
Revises: 20261005_110000
Create Date: 2026-10-05 15:00:00.000000

The owner's private copy of a photo is now kept in the owner's own folder,
`private/users/<account id>/insights/<random>.jpg` (96 characters), so one
person's photos can be exported or deleted together. The column held 64. The
public copy keeps its short key, which names nobody. Going back fails while a
longer key is stored, rather than cutting a key in two.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261005_150000"
down_revision: str | Sequence[str] | None = "20261005_110000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"


def upgrade() -> None:
    op.alter_column(
        "insights",
        "photo_key",
        type_=sa.String(128),
        existing_type=sa.String(64),
        existing_nullable=True,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.alter_column(
        "insights",
        "photo_key",
        type_=sa.String(64),
        existing_type=sa.String(128),
        existing_nullable=True,
        schema=SCHEMA,
    )
