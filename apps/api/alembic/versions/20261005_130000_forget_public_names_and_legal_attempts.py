"""forget_public_names_and_legal_attempts

Revision ID: 20261005_130000
Revises: 20261005_120000
Create Date: 2026-10-05 13:00:00.000000

Decision 63. `users.public_name` (the name a member once chose for the network) is read by
nothing any more: public answers carry the real full name only with its consent. The column is
emptied for data minimisation and kept so the model and the earlier migrations still agree.
`login_attempts.kind` gains `legal_accept`, the counter of `POST /auth/legal/accept`.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261005_130000"
down_revision: str | Sequence[str] | None = "20261005_120000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"
CONSTRAINT = "ck_login_attempts_kind"
BEFORE = (
    "kind IN ('login', 'signup', 'google_start', 'resend_verification', "
    "'forgot_password', 'support', 'email_token')"
)
AFTER = (
    "kind IN ('login', 'signup', 'google_start', 'resend_verification', "
    "'forgot_password', 'support', 'email_token', 'legal_accept')"
)


def _replace_constraint(condition: str) -> None:
    op.drop_constraint(op.f(CONSTRAINT), "login_attempts", schema=SCHEMA, type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "login_attempts", condition, schema=SCHEMA)


def upgrade() -> None:
    op.execute(f"UPDATE {SCHEMA}.users SET public_name = NULL WHERE public_name IS NOT NULL")
    _replace_constraint(AFTER)


def downgrade() -> None:
    """Narrow the constraint again; the emptied names are gone for good."""
    op.execute(f"DELETE FROM {SCHEMA}.login_attempts WHERE kind = 'legal_accept'")
    _replace_constraint(BEFORE)
