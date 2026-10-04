"""add_profile_reduced_motion

Revision ID: 20261004_192500
Revises: 20261004_192000
Create Date: 2026-10-04 19:00:00.000000

The motion preference follows the account across devices, like the theme:
`profiles.reduced_motion` is `system`, `on` or `off`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261004_192500"
down_revision: str | Sequence[str] | None = "20261004_192000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"


def upgrade() -> None:
    op.add_column(
        "profiles",
        sa.Column("reduced_motion", sa.String(length=32), server_default="system", nullable=False),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        op.f("ck_profiles_reduced_motion"),
        "profiles",
        "reduced_motion IN ('system', 'on', 'off')",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_profiles_reduced_motion"), "profiles", schema=SCHEMA, type_="check")
    op.drop_column("profiles", "reduced_motion", schema=SCHEMA)
