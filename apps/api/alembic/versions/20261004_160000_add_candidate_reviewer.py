"""add_candidate_reviewer

Revision ID: 20261004_160000
Revises: 20261004_150000
Create Date: 2026-10-04 16:00:00.000000

Which admin accepted or rejected an ontology candidate. A plain id with no foreign
key: deleting that account must not fail and must not rewrite the review.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261004_160000"
down_revision: str | Sequence[str] | None = "20261004_150000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"


def upgrade() -> None:
    op.add_column(
        "ontology_candidates", sa.Column("reviewed_by", sa.Uuid(), nullable=True), schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_column("ontology_candidates", "reviewed_by", schema=SCHEMA)
