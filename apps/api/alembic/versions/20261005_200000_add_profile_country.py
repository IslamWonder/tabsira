"""add_profile_country

Revision ID: 20261005_200000
Revises: 20261005_190000
Create Date: 2026-10-05 20:00:00.000000

Decision 67. `profiles.country` is the ISO2 code of the country a person chose to declare, empty
for everyone until they do; its shape is checked here and its existence against GeoNames by the
API (the `geodata` schema is reinstalled from its dump, so no foreign key points into it).
`profiles.show_country` mirrors the latest `public_country` consent row (false for everyone:
nobody consented), and the consent kind joins the CHECK constraint of `consents.kind`. Written by
hand after the model.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261005_200000"
down_revision: str | Sequence[str] | None = "20261005_190000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"
CONSTRAINT = "ck_consents_kind"
BEFORE = (
    "kind IN ('terms', 'privacy', 'photo_storage', 'personalization', 'memory', 'public_full_name')"
)
AFTER = (
    "kind IN ('terms', 'privacy', 'photo_storage', 'personalization', 'memory', "
    "'public_full_name', 'public_country')"
)


def _replace_constraint(condition: str) -> None:
    op.drop_constraint(op.f(CONSTRAINT), "consents", schema=SCHEMA, type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "consents", condition, schema=SCHEMA)


def upgrade() -> None:
    op.add_column("profiles", sa.Column("country", sa.String(2), nullable=True), schema=SCHEMA)
    op.create_check_constraint(
        op.f("ck_profiles_country_format"), "profiles", "country ~ '^[A-Z]{2}$'", schema=SCHEMA
    )
    op.add_column(
        "profiles",
        sa.Column("show_country", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        schema=SCHEMA,
    )
    _replace_constraint(AFTER)


def downgrade() -> None:
    """Drop the columns and the new kind; its consent rows go too (a development tool only)."""
    op.execute(f"DELETE FROM {SCHEMA}.consents WHERE kind = 'public_country'")
    _replace_constraint(BEFORE)
    op.drop_column("profiles", "show_country", schema=SCHEMA)
    op.drop_constraint(op.f("ck_profiles_country_format"), "profiles", schema=SCHEMA, type_="check")
    op.drop_column("profiles", "country", schema=SCHEMA)
