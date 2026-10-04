"""add_privacy_consent_kind

Revision ID: 20261004_181000
Revises: 20261004_180000
Create Date: 2026-10-04 18:10:00.000000

Decision 35: the terms of use and the privacy policy are accepted separately, each with its
own version. `consents.kind` gains `privacy`; `terms` now means the terms of use alone. Rows
stay append-only: this only widens the CHECK constraint on the kind.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261004_181000"
down_revision: str | Sequence[str] | None = "20261004_180000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"
CONSTRAINT = "ck_consents_kind"
BEFORE = "kind IN ('terms', 'photo_storage', 'personalization', 'memory')"
AFTER = "kind IN ('terms', 'privacy', 'photo_storage', 'personalization', 'memory')"


def _replace_constraint(condition: str) -> None:
    op.drop_constraint(op.f(CONSTRAINT), "consents", schema=SCHEMA, type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "consents", condition, schema=SCHEMA)


def upgrade() -> None:
    _replace_constraint(AFTER)


def downgrade() -> None:
    """
    Remove every `privacy` row, then narrow the constraint again.

    This deletes history that is otherwise append-only, on purpose: the narrower constraint
    cannot hold the new kind, and the append-only guard refuses updates but not deletes. A
    downgrade is a development tool; running it in production loses the privacy acceptances,
    and every account is then asked again. (Also noted for the support form: a filled
    honeypot returns before the limit is counted, so a bot's answer is quick and uncounted.)
    """
    op.execute(f"DELETE FROM {SCHEMA}.consents WHERE kind = 'privacy'")
    _replace_constraint(BEFORE)
