"""
Append-only time series (decision 13): scan stage events, AI calls and evidence exposures.

Each table is a TimescaleDB hypertable partitioned on `at`, so its primary key
holds `at`. Old chunks are compressed and then dropped by policies set from the
settings (`src/cli/timeseries_policy.py` applies changed values). None of them
holds a photo, a profile field, a typed text, a prompt or an answer.

- `scan_events`: how long each stage of a scan took and how it ended. The scan
  id is a plain column with no foreign key, so a deleted scan leaves only
  anonymous timings behind.
- `ai_calls`: one row per `CallRecord` (provider, model, stage, attempts,
  tokens, cost, latency, error code), for the cost and latency views.
- `evidence_exposures`: what a learner completed and was shown (the verse and
  hadith by reference, the concept, the unit), which the engine reads to vary
  the texts it shows (v2 §11). It names its owner, so it is deleted with the
  account and merged with the guest's rows at the first sign-in.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DDL,
    BigInteger,
    Boolean,
    Float,
    Identity,
    Index,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    Uuid,
    event,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from src.config import (
    DEFAULT_AI_CALLS_COMPRESS_AFTER_DAYS,
    DEFAULT_AI_CALLS_RETENTION_DAYS,
    DEFAULT_EXPOSURES_COMPRESS_AFTER_DAYS,
    DEFAULT_EXPOSURES_RETENTION_DAYS,
    DEFAULT_SCAN_EVENTS_COMPRESS_AFTER_DAYS,
    DEFAULT_SCAN_EVENTS_RETENTION_DAYS,
)
from src.models.base import Base, created_at_column
from src.models.scan import GUEST_KEY_LENGTH


class ScanEvent(Base):
    """One stage of one run of a scan: its name, how it ended, how long it took."""

    __tablename__ = "scan_events"
    __table_args__ = (
        PrimaryKeyConstraint("at", "id", name="pk_scan_events"),
        Index("ix_scan_events_scan_id_at", "scan_id", "at"),
    )

    at: Mapped[datetime] = created_at_column()
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True))
    scan_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    run: Mapped[int] = mapped_column(Integer)
    # validate, detect, understand, sensitivity, searching, verifying, composing, save, job
    stage: Mapped[str] = mapped_column(String(32))
    # done, skipped or failed
    status: Mapped[str] = mapped_column(String(16))
    ms: Mapped[int | None] = mapped_column(Integer)
    # A stable code: why a stage was skipped or failed, or how a run ended.
    code: Mapped[str | None] = mapped_column(String(64))


class AiCall(Base):
    """One model call, as its `CallRecord` describes it; never the prompt or the answer."""

    __tablename__ = "ai_calls"
    __table_args__ = (
        PrimaryKeyConstraint("at", "id", name="pk_ai_calls"),
        Index("ix_ai_calls_scan_id_at", "scan_id", "at"),
    )

    at: Mapped[datetime] = created_at_column()
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True))
    # What the call served: a scan, or the chat of an insight.
    scan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    insight_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    provider: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(128))
    stage: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(16))
    attempts: Mapped[int] = mapped_column(SmallInteger)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    reasoning_tokens: Mapped[int] = mapped_column(Integer)
    cached_input_tokens: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    latency_ms: Mapped[int] = mapped_column(Integer)
    ok: Mapped[bool] = mapped_column(Boolean)
    error_code: Mapped[str | None] = mapped_column(String(32))
    finish_reason: Mapped[str | None] = mapped_column(String(32))
    retried_errors: Mapped[list[str]] = mapped_column(ARRAY(Text))


class EvidenceExposure(Base):
    """A verse, a hadith and a concept a learner completed (or found in a treasure), by reference."""

    __tablename__ = "evidence_exposures"
    __table_args__ = (
        PrimaryKeyConstraint("at", "id", name="pk_evidence_exposures"),
        Index("ix_evidence_exposures_user_id_at", "user_id", "at"),
        Index("ix_evidence_exposures_guest_key_at", "guest_key", "at"),
    )

    at: Mapped[datetime] = created_at_column()
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True))
    # The owner, as in every learner table, with no foreign key: the account
    # deletion and the guest expiry delete these rows themselves.
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    guest_key: Mapped[str | None] = mapped_column(String(GUEST_KEY_LENGTH))
    insight_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    # `completed` («تمّ») or `treasure` (a revealed treasure).
    kind: Mapped[str] = mapped_column(String(16))
    quran_surah: Mapped[int | None] = mapped_column(SmallInteger)
    quran_ayah: Mapped[int | None] = mapped_column(SmallInteger)
    hadith_collection: Mapped[str | None] = mapped_column(String(32))
    hadith_number: Mapped[str | None] = mapped_column(String(32))
    concept: Mapped[str | None] = mapped_column(String(80))
    learning_unit_id: Mapped[str | None] = mapped_column(String(16))


# Chunk size and how each table is compressed. The migration that creates the tables
# runs the same statements; these copies build them when a test schema is made from
# the models, and a test keeps the two identical.
HYPERTABLES: dict[str, tuple[int, str]] = {
    "scan_events": (7, "scan_id"),
    "ai_calls": (7, "provider, model"),
    "evidence_exposures": (30, "user_id, guest_key"),
}
DEFAULT_POLICY_DAYS: dict[str, tuple[int, int]] = {
    "scan_events": (DEFAULT_SCAN_EVENTS_RETENTION_DAYS, DEFAULT_SCAN_EVENTS_COMPRESS_AFTER_DAYS),
    "ai_calls": (DEFAULT_AI_CALLS_RETENTION_DAYS, DEFAULT_AI_CALLS_COMPRESS_AFTER_DAYS),
    "evidence_exposures": (DEFAULT_EXPOSURES_RETENTION_DAYS, DEFAULT_EXPOSURES_COMPRESS_AFTER_DAYS),
}


def hypertable_statements(table: str) -> tuple[str, str]:
    """Return the statements that make `app.<table>` a compressed hypertable."""
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
    """Return the statements that set the compression and retention policies of a table, replacing any."""
    name = f"app.{table}"
    return (
        f"SELECT remove_compression_policy('{name}', if_exists => true)",
        f"SELECT add_compression_policy('{name}', INTERVAL '{int(compress_after_days)} days')",
        f"SELECT remove_retention_policy('{name}', if_exists => true)",
        f"SELECT add_retention_policy('{name}', INTERVAL '{int(retention_days)} days')",
    )


for _table, (_retention, _compress) in DEFAULT_POLICY_DAYS.items():
    for _statement in (
        *hypertable_statements(_table),
        *policy_statements(_table, _retention, _compress),
    ):
        # SQLAlchemy ships DDL without type hints.
        _ddl = DDL(_statement)  # type: ignore[no-untyped-call]
        event.listen(
            Base.metadata.tables[f"app.{_table}"],
            "after_create",
            _ddl.execute_if(dialect="postgresql"),
        )
