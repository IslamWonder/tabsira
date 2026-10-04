"""
The admin audit log: who did what in the admin area, append-only, kept for a limited time.

Decision 13 puts append-only time series in TimescaleDB, partitioned on their time
column; this is the first one. The table is a hypertable on `at`, so the primary key
holds `at`. A trigger refuses every UPDATE and DELETE, which makes the log
append-only even for the application's own role; old rows leave only when
TimescaleDB drops a whole chunk (the retention policy), which does not run row
triggers. Chunks older than a set age are compressed.

A row names the admin and what they touched, never what they wrote: `details` holds
field names and counts, built by `admin_audit_service` from typed arguments, so a value
cannot reach it. The admin's id and the record's id are plain columns, with no foreign
key: deleting an account must neither fail nor rewrite the log.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    DDL,
    BigInteger,
    Identity,
    Index,
    PrimaryKeyConstraint,
    String,
    Uuid,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.config import DEFAULT_AUDIT_COMPRESS_AFTER_DAYS, DEFAULT_AUDIT_RETENTION_DAYS
from src.models.base import Base, created_at_column, string_enum

AUDIT_TABLE = "app.admin_audit_log"
# A chunk holds a week: small enough for the retention to drop one at a time, large
# enough to keep the chunk count low over 400 days.
CHUNK_INTERVAL_DAYS = 7


class AuditAction(StrEnum):
    """What an audit row records."""

    SIGN_IN = "sign_in"
    SIGN_IN_FAILED = "sign_in_failed"
    SIGN_OUT = "sign_out"
    LIST = "list"  # a list page of one view
    VIEW = "view"  # the page of one record
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    BULK_ACTION = "bulk_action"  # an action on the records ticked in a list
    TWO_FACTOR_ENABLED = "two_factor_enabled"
    TWO_FACTOR_DISABLED = "two_factor_disabled"
    # Done on the server's command line, not in the admin area.
    ADMIN_GRANTED = "admin_granted"
    ADMIN_REVOKED = "admin_revoked"
    TWO_FACTOR_RESET = "two_factor_reset"


class AdminAuditLog(Base):
    """
    One thing an admin did, or tried to do, in the admin area.

    `admin_user_id` is the account that acted: for a failed sign-in, the account the
    attempt named when there is one, and nothing otherwise (the address that was typed
    is never kept). `model` and `record_id` say what was touched, `details` how.
    """

    __tablename__ = "admin_audit_log"
    __table_args__ = (
        # The partitioning column is part of the key: a hypertable requires it.
        PrimaryKeyConstraint("at", "id", name="pk_admin_audit_log"),
        Index("ix_admin_audit_log_admin_user_id_at", "admin_user_id", "at"),
    )

    at: Mapped[datetime] = created_at_column()
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True))
    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    action: Mapped[AuditAction] = mapped_column(string_enum(AuditAction, "action"))
    # The admin view's identity (`user`, `ontology-candidate`, ...) when a model was involved.
    model: Mapped[str | None] = mapped_column(String(64))
    record_id: Mapped[str | None] = mapped_column(String(256))
    # Field names, a reason code, a count: see `admin_audit_service.details_of`.
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # A keyed hash of the address, never the address.
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(256))


# The statements below are written out again in the migration that creates the table;
# these copies build the same thing when a test schema is created from the models. A
# test keeps the two identical.
HYPERTABLE_STATEMENTS = (
    f"""
    SELECT create_hypertable(
        '{AUDIT_TABLE}', by_range('at', INTERVAL '{CHUNK_INTERVAL_DAYS} days'),
        create_default_indexes => false
    )
    """,
    """
    CREATE OR REPLACE FUNCTION app.admin_audit_log_forbid_change() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'the admin audit log is append-only'
            USING ERRCODE = 'integrity_constraint_violation';
    END
    $$
    """,
    f"""
    CREATE TRIGGER admin_audit_log_forbid_change BEFORE UPDATE OR DELETE ON {AUDIT_TABLE}
    FOR EACH ROW EXECUTE FUNCTION app.admin_audit_log_forbid_change()
    """,
    f"""
    ALTER TABLE {AUDIT_TABLE} SET (
        timescaledb.compress,
        timescaledb.compress_segmentby = 'admin_user_id',
        timescaledb.compress_orderby = 'at DESC, id DESC'
    )
    """,
)


def policy_statements(retention_days: int, compress_after_days: int) -> tuple[str, ...]:
    """
    Return the statements that set the compression and retention policies, replacing any.

    The migration sets them from the settings; `python -m src.cli.audit_policy` runs
    these again when the settings change. The days are integers the settings bound.
    """
    return (
        f"SELECT remove_compression_policy('{AUDIT_TABLE}', if_exists => true)",
        f"SELECT add_compression_policy('{AUDIT_TABLE}', INTERVAL '{int(compress_after_days)} days')",
        f"SELECT remove_retention_policy('{AUDIT_TABLE}', if_exists => true)",
        f"SELECT add_retention_policy('{AUDIT_TABLE}', INTERVAL '{int(retention_days)} days')",
    )


for _statement in (
    *HYPERTABLE_STATEMENTS,
    *policy_statements(DEFAULT_AUDIT_RETENTION_DAYS, DEFAULT_AUDIT_COMPRESS_AFTER_DAYS),
):
    # SQLAlchemy ships DDL without type hints.
    _ddl = DDL(_statement)  # type: ignore[no-untyped-call]
    event.listen(AdminAuditLog.__table__, "after_create", _ddl.execute_if(dialect="postgresql"))
