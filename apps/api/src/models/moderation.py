"""
The moderation log: every decision about a post or a comment, append-only.

Decision 13 puts append-only time series in TimescaleDB, partitioned on their time column;
this is the second one after the admin audit log. The table is a hypertable on `at`, so the
primary key holds `at`. A trigger refuses every UPDATE and DELETE, which makes the log
append-only even for the application's own role; old rows leave only when TimescaleDB drops
a whole chunk (the retention policy), which does not run row triggers. Chunks older than a
set age are compressed.

A row says what was decided, by whom (the guard, a moderator, a report threshold or the
owner) and why, as a code and the guard's category scores. It never holds the text that was
judged. The ids are plain columns with no foreign key: deleting an account must neither fail
nor rewrite the log, and the log names no author, only the item.
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

from src.config import DEFAULT_MODERATION_COMPRESS_AFTER_DAYS, DEFAULT_MODERATION_RETENTION_DAYS
from src.models.base import Base, created_at_column, string_enum

MODERATION_TABLE = "app.moderation_actions"
# A chunk holds a week, like the admin audit log.
CHUNK_INTERVAL_DAYS = 7


class ModerationTarget(StrEnum):
    POST = "post"
    COMMENT = "comment"


class ModerationActionKind(StrEnum):
    """What was decided."""

    PUBLISHED = "published"  # visible to its audience
    HELD = "held"  # waits for a person
    REJECTED = "rejected"  # refused; the author is told why
    REMOVED = "removed"  # taken down after it was published
    RESTORED = "restored"  # a removal or a rejection reversed
    WITHDRAWN = "withdrawn"  # the author took it back


class ModerationSource(StrEnum):
    """Who decided."""

    GUARD = "guard"  # the automatic text guard
    MODERATOR = "moderator"  # a person in the admin area
    REPORTS = "reports"  # enough reports moved a published item back to the queue
    OWNER = "owner"  # the author


class ModerationAction(Base):
    """One decision, with its source and its reason code."""

    __tablename__ = "moderation_actions"
    __table_args__ = (
        # The partitioning column is part of the key: a hypertable requires it.
        PrimaryKeyConstraint("at", "id", name="pk_moderation_actions"),
        Index("ix_moderation_actions_target_at", "target_type", "target_id", "at"),
    )

    at: Mapped[datetime] = created_at_column()
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True))
    target_type: Mapped[ModerationTarget] = mapped_column(
        string_enum(ModerationTarget, "target_type")
    )
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    action: Mapped[ModerationActionKind] = mapped_column(
        string_enum(ModerationActionKind, "action")
    )
    source: Mapped[ModerationSource] = mapped_column(string_enum(ModerationSource, "source"))
    # The moderator's account, for a decision a person made.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    reason: Mapped[str | None] = mapped_column(String(64))
    # The guard's flagged categories and rounded scores; never the text.
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


# The statements below are written out again in the migration that creates the table; these
# copies build the same thing when a test schema is created from the models. A test keeps
# the two identical.
HYPERTABLE_STATEMENTS = (
    f"""
    SELECT create_hypertable(
        '{MODERATION_TABLE}', by_range('at', INTERVAL '{CHUNK_INTERVAL_DAYS} days'),
        create_default_indexes => false
    )
    """,
    """
    CREATE OR REPLACE FUNCTION app.moderation_actions_forbid_change() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'the moderation log is append-only'
            USING ERRCODE = 'integrity_constraint_violation';
    END
    $$
    """,
    f"""
    CREATE TRIGGER moderation_actions_forbid_change BEFORE UPDATE OR DELETE ON {MODERATION_TABLE}
    FOR EACH ROW EXECUTE FUNCTION app.moderation_actions_forbid_change()
    """,
    f"""
    ALTER TABLE {MODERATION_TABLE} SET (
        timescaledb.compress,
        timescaledb.compress_segmentby = 'target_type',
        timescaledb.compress_orderby = 'at DESC, id DESC'
    )
    """,
)


def policy_statements(retention_days: int, compress_after_days: int) -> tuple[str, ...]:
    """
    Return the statements that set the compression and retention policies, replacing any.

    The migration sets them from the settings; the days are integers the settings bound.
    """
    return (
        f"SELECT remove_compression_policy('{MODERATION_TABLE}', if_exists => true)",
        f"SELECT add_compression_policy('{MODERATION_TABLE}', INTERVAL '{int(compress_after_days)} days')",
        f"SELECT remove_retention_policy('{MODERATION_TABLE}', if_exists => true)",
        f"SELECT add_retention_policy('{MODERATION_TABLE}', INTERVAL '{int(retention_days)} days')",
    )


for _statement in (
    *HYPERTABLE_STATEMENTS,
    *policy_statements(DEFAULT_MODERATION_RETENTION_DAYS, DEFAULT_MODERATION_COMPRESS_AFTER_DAYS),
):
    # SQLAlchemy ships DDL without type hints.
    _ddl = DDL(_statement)  # type: ignore[no-untyped-call]
    event.listen(ModerationAction.__table__, "after_create", _ddl.execute_if(dialect="postgresql"))
