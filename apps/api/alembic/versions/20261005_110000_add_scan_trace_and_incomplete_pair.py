"""add_scan_trace_and_incomplete_pair

Revision ID: 20261005_110000
Revises: 20261005_100000
Create Date: 2026-10-05 11:00:00.000000

The rebuilt insight engine (the brief of 2026-10-05): `scans.engine_trace`
holds the reviewable record of the last run (the intents with the planner's
guarded words and queries, candidate ids and their channels, verdicts, reasons
and the choice; never a stored text, never the learner), and `outcome` gains `incomplete_evidence_pair`, the honest state of a
scan whose accepted evidence cannot be shown yet because its only fitting
hadith waits for an editor's ruling. Written by hand after the model.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261005_110000"
down_revision: str | Sequence[str] | None = "20261005_100000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"
CONSTRAINT = "ck_scans_outcome"
BEFORE = "outcome IN ('insights', 'needs_clarification', 'no_relevant_evidence')"
AFTER = (
    "outcome IN ('insights', 'needs_clarification', 'no_relevant_evidence', "
    "'incomplete_evidence_pair')"
)


def upgrade() -> None:
    op.add_column(
        "scans",
        sa.Column("engine_trace", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema=SCHEMA,
    )
    op.drop_constraint(op.f(CONSTRAINT), "scans", schema=SCHEMA, type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "scans", AFTER, schema=SCHEMA)


def downgrade() -> None:
    op.execute(
        f"UPDATE {SCHEMA}.scans SET outcome = 'no_relevant_evidence' "
        "WHERE outcome = 'incomplete_evidence_pair'"
    )
    op.drop_constraint(op.f(CONSTRAINT), "scans", schema=SCHEMA, type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "scans", BEFORE, schema=SCHEMA)
    op.drop_column("scans", "engine_trace", schema=SCHEMA)
