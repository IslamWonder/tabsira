"""add_oauth_state_acceptance

Revision ID: 20261004_180000
Revises: 20261004_170000
Create Date: 2026-10-04 18:00:00.000000

Decision 35: a Google sign-up accepts the terms and the privacy policy too. The versions the
person ticked travel with the sign-in in flight, so the callback can record them when it
creates the account. They live as long as the state (minutes) and are deleted with it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261004_180000"
down_revision: str | Sequence[str] | None = "20261004_170000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"


def upgrade() -> None:
    for column in ("accepted_terms_version", "accepted_privacy_version"):
        op.add_column(
            "oauth_states", sa.Column(column, sa.String(length=32), nullable=True), schema=SCHEMA
        )


def downgrade() -> None:
    for column in ("accepted_privacy_version", "accepted_terms_version"):
        op.drop_column("oauth_states", column, schema=SCHEMA)
