"""create_admin_audit_log

Revision ID: 20261004_140000
Revises: 20261004_123000
Create Date: 2026-10-04 14:00:00.000000

The admin audit log, a TimescaleDB hypertable partitioned on its time column
(decision 13). The primary key holds the time column, a trigger refuses UPDATE and
DELETE, and the compression and retention policies come from ADMIN_AUDIT_* in the
settings (400 and 30 days by default). Rows leave only when the retention policy
drops a whole chunk, which does not run row triggers.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from src.config import get_settings

revision: str = "20261004_140000"
down_revision: str | Sequence[str] | None = "20261004_123000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"
TABLE = "app.admin_audit_log"
ACTIONS = (
    "sign_in",
    "sign_in_failed",
    "sign_out",
    "list",
    "view",
    "create",
    "update",
    "delete",
    "bulk_action",
    "two_factor_enabled",
    "two_factor_disabled",
    "admin_granted",
    "admin_revoked",
    "two_factor_reset",
)


def upgrade() -> None:
    settings = get_settings()
    actions = ", ".join(f"'{action}'" for action in ACTIONS)
    op.create_table(
        "admin_audit_log",
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("admin_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("record_id", sa.String(length=256), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
        sa.CheckConstraint(f"action IN ({actions})", name=op.f("ck_admin_audit_log_action")),
        sa.PrimaryKeyConstraint("at", "id", name="pk_admin_audit_log"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_admin_audit_log_admin_user_id_at",
        "admin_audit_log",
        ["admin_user_id", "at"],
        schema=SCHEMA,
    )
    op.execute(
        f"""
        SELECT create_hypertable(
            '{TABLE}', by_range('at', INTERVAL '7 days'),
            create_default_indexes => false
        )
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.admin_audit_log_forbid_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'the admin audit log is append-only'
                USING ERRCODE = 'integrity_constraint_violation';
        END
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER admin_audit_log_forbid_change BEFORE UPDATE OR DELETE ON {TABLE}
        FOR EACH ROW EXECUTE FUNCTION app.admin_audit_log_forbid_change()
        """
    )
    op.execute(
        f"""
        ALTER TABLE {TABLE} SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'admin_user_id',
            timescaledb.compress_orderby = 'at DESC, id DESC'
        )
        """
    )
    compress_after = int(settings.admin_audit_compress_after_days)
    retention = int(settings.admin_audit_retention_days)
    op.execute(f"SELECT add_compression_policy('{TABLE}', INTERVAL '{compress_after} days')")
    op.execute(f"SELECT add_retention_policy('{TABLE}', INTERVAL '{retention} days')")


def downgrade() -> None:
    # Dropping the hypertable drops its chunks, its trigger and its two policies.
    op.drop_table("admin_audit_log", schema=SCHEMA)
    op.execute("DROP FUNCTION app.admin_audit_log_forbid_change()")
