"""add_support_attempt_kind

Revision ID: 20261004_182000
Revises: 20261004_181000
Create Date: 2026-10-04 18:20:00.000000

The support form is rate limited in PostgreSQL like the sign-in routes, so the limit holds
across every worker: `login_attempts.kind` gains `support`.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261004_182000"
down_revision: str | Sequence[str] | None = "20261004_181000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"
CONSTRAINT = "ck_login_attempts_kind"
BEFORE = (
    "kind IN ('login', 'signup', 'google_start', 'resend_verification', "
    "'forgot_password', 'email_token')"
)
AFTER = (
    "kind IN ('login', 'signup', 'google_start', 'resend_verification', "
    "'forgot_password', 'support', 'email_token')"
)


def _replace_constraint(condition: str) -> None:
    op.drop_constraint(op.f(CONSTRAINT), "login_attempts", schema=SCHEMA, type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "login_attempts", condition, schema=SCHEMA)


def upgrade() -> None:
    _replace_constraint(AFTER)


def downgrade() -> None:
    # Attempts are only counters; the narrower constraint cannot hold the new kind.
    op.execute(f"DELETE FROM {SCHEMA}.login_attempts WHERE kind = 'support'")
    _replace_constraint(BEFORE)
