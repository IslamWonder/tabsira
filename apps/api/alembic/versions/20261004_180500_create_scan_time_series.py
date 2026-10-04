"""create_scan_time_series

Revision ID: 20261004_180500
Revises: 20261004_180000
Create Date: 2026-10-04 18:05:00.000000

Three TimescaleDB hypertables partitioned on `at` (decision 13): the stage
events of scans, the AI calls and the evidence exposures of learners. Each is
compressed after a while and dropped after its retention, both from the
settings (SCAN_EVENTS_*, AI_CALLS_*, EVIDENCE_EXPOSURES_*); a change of those
values is applied by `python -m src.cli.timeseries_policy`. The statements are
written out here as `src/models/timeseries.py` writes them for a schema built
from the models; a test keeps the two identical.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from src.config import get_settings

revision: str = "20261004_180500"
down_revision: str | Sequence[str] | None = "20261004_180000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"
# Table: (days per chunk, compression segments).
HYPERTABLES = {
    "scan_events": (7, "scan_id"),
    "ai_calls": (7, "provider, model"),
    "evidence_exposures": (30, "user_id, guest_key"),
}


def hypertable_statements(table: str) -> tuple[str, str]:
    chunk_days, segment_by = HYPERTABLES[table]
    return (
        f"""
        SELECT create_hypertable(
            'app.{table}', by_range('at', INTERVAL '{chunk_days} days'),
            create_default_indexes => false
        )
        """,
        f"""
        ALTER TABLE app.{table} SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = '{segment_by}',
            timescaledb.compress_orderby = 'at DESC, id DESC'
        )
        """,
    )


def policy_statements(table: str, retention_days: int, compress_after_days: int) -> tuple[str, ...]:
    name = f"app.{table}"
    return (
        f"SELECT remove_compression_policy('{name}', if_exists => true)",
        f"SELECT add_compression_policy('{name}', INTERVAL '{int(compress_after_days)} days')",
        f"SELECT remove_retention_policy('{name}', if_exists => true)",
        f"SELECT add_retention_policy('{name}', INTERVAL '{int(retention_days)} days')",
    )


def _at() -> sa.Column[sa.DateTime]:
    return sa.Column(
        "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _id() -> sa.Column[sa.BigInteger]:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "scan_events",
        _at(),
        _id(),
        sa.Column("scan_id", sa.Uuid(), nullable=False),
        sa.Column("run", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("ms", sa.Integer(), nullable=True),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("at", "id", name="pk_scan_events"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_scan_events_scan_id_at", "scan_events", ["scan_id", "at"], unique=False, schema=SCHEMA
    )
    op.create_table(
        "ai_calls",
        _at(),
        _id(),
        sa.Column("scan_id", sa.Uuid(), nullable=True),
        sa.Column("insight_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(length=32), nullable=True),
        sa.Column("finish_reason", sa.String(length=32), nullable=True),
        sa.Column("retried_errors", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("at", "id", name="pk_ai_calls"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_ai_calls_scan_id_at", "ai_calls", ["scan_id", "at"], unique=False, schema=SCHEMA
    )
    op.create_table(
        "evidence_exposures",
        _at(),
        _id(),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("guest_key", sa.String(length=64), nullable=True),
        sa.Column("insight_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("quran_surah", sa.SmallInteger(), nullable=True),
        sa.Column("quran_ayah", sa.SmallInteger(), nullable=True),
        sa.Column("hadith_collection", sa.String(length=32), nullable=True),
        sa.Column("hadith_number", sa.String(length=32), nullable=True),
        sa.Column("concept", sa.String(length=80), nullable=True),
        sa.Column("learning_unit_id", sa.String(length=16), nullable=True),
        sa.PrimaryKeyConstraint("at", "id", name="pk_evidence_exposures"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_evidence_exposures_user_id_at",
        "evidence_exposures",
        ["user_id", "at"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_index(
        "ix_evidence_exposures_guest_key_at",
        "evidence_exposures",
        ["guest_key", "at"],
        unique=False,
        schema=SCHEMA,
    )

    settings = get_settings()
    for table in HYPERTABLES:
        for statement in hypertable_statements(table):
            op.execute(statement)
        for statement in policy_statements(
            table,
            getattr(settings, f"{table}_retention_days"),
            getattr(settings, f"{table}_compress_after_days"),
        ):
            op.execute(statement)


def downgrade() -> None:
    # Dropping a hypertable drops its chunks and its two policies.
    for table in reversed(HYPERTABLES):
        op.drop_table(table, schema=SCHEMA)
