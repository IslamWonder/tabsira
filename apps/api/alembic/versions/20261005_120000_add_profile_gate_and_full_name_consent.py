"""add_profile_gate_and_full_name_consent

Revision ID: 20261005_120000
Revises: 20261005_110000
Create Date: 2026-10-05 12:00:00.000000

Decision 64. `profiles.profile_completed_at` is set once the person answered every question of
the profile; empty means the scan and the chat refuse (`profile_required`). It is not
backfilled: no existing account ever answered the religious background or the gender through a
form that offered «أفضّل عدم الإجابة», so each is asked once at its next visit. `users.public_full_name`
mirrors the latest `public_full_name` consent row (false for everyone: nobody consented), and the
consent kind joins the CHECK constraint of `consents.kind`. Written by hand after the model.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261005_120000"
down_revision: str | Sequence[str] | None = "20261005_170000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"
CONSTRAINT = "ck_consents_kind"
BEFORE = "kind IN ('terms', 'privacy', 'photo_storage', 'personalization', 'memory')"
AFTER = (
    "kind IN ('terms', 'privacy', 'photo_storage', 'personalization', 'memory', 'public_full_name')"
)


def _replace_constraint(condition: str) -> None:
    op.drop_constraint(op.f(CONSTRAINT), "consents", schema=SCHEMA, type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "consents", condition, schema=SCHEMA)


def upgrade() -> None:
    op.add_column(
        "profiles",
        sa.Column("profile_completed_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "users",
        sa.Column(
            "public_full_name", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        schema=SCHEMA,
    )
    _replace_constraint(AFTER)


def downgrade() -> None:
    """Drop the columns and the new kind; its consent rows go too (a development tool only)."""
    op.execute(f"DELETE FROM {SCHEMA}.consents WHERE kind = 'public_full_name'")
    _replace_constraint(BEFORE)
    op.drop_column("users", "public_full_name", schema=SCHEMA)
    op.drop_column("profiles", "profile_completed_at", schema=SCHEMA)
