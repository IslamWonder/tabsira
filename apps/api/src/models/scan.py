"""
Scans, the insights they produce, and the three chat messages of an insight.

Everything here belongs to one owner: an account (`user_id`) or a guest
(`guest_key`, the hash of the random key of a signed cookie), never both.
Deleting the account or letting the guest expire deletes it all (ON DELETE
CASCADE). No photo is stored here: a scan keeps the meaning of its scene, the
photo lives only in the temporary store for an hour (never for a sensitive
scene). An insight keeps its evidence by reference only; the text of a verse or
a hadith is always read from the scripture store when the insight is shown.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, created_at_column, string_enum
from src.models.public_id import public_id_pk

GUEST_KEY_LENGTH = 64
ONE_OWNER = "num_nonnulls(user_id, guest_key) = 1"


class ScanStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ScanSource(StrEnum):
    UPLOAD = "upload"
    URL = "url"


class ScanOutcome(StrEnum):
    """What a finished scan found (v2 §8 and §26): insights, a question, or no reliable link."""

    INSIGHTS = "insights"
    NEEDS_CLARIFICATION = "needs_clarification"
    NO_RELEVANT_EVIDENCE = "no_relevant_evidence"


class InsightOrigin(StrEnum):
    SCAN = "scan"
    # A copy of a prepared tutorial insight, kept so it can be completed like any other.
    TUTORIAL = "tutorial"


class ActionState(StrEnum):
    """What the learner declared about the small step: a statement, never a proof (tajriba §9)."""

    DONE = "done"
    LATER = "later"


class ChatStatus(StrEnum):
    # A slot is held while the answer is written; a failed answer gives the slot back.
    PENDING = "pending"
    ANSWERED = "answered"


class Guest(Base):
    """A browser that used the app without an account; known by the hash of its cookie key."""

    __tablename__ = "guests"
    __table_args__ = (CheckConstraint("char_length(key) = 64", name="key_length"),)

    key: Mapped[str] = mapped_column(String(GUEST_KEY_LENGTH), primary_key=True)
    created_at: Mapped[datetime] = created_at_column()
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


def _user_column() -> Mapped[uuid.UUID | None]:
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"))


def _guest_column() -> Mapped[str | None]:
    return mapped_column(String(GUEST_KEY_LENGTH), ForeignKey("guests.key", ondelete="CASCADE"))


class Scan(Base):
    """
    One photo looked at, and what came of it.

    `run` counts the engine runs of the scan: the first, then one per focus or
    clarification. A job carries the run it was queued for, so a late job of an
    earlier run never overwrites the current one. `scene` is the verified scene
    (model-written description, entities and boxes as ratios); it never holds
    the photo, its location or anything about the person who took it.
    """

    # Read the database-set `updated_at` back with the UPDATE: no lazy load in async code.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __tablename__ = "scans"
    __table_args__ = (
        CheckConstraint(ONE_OWNER, name="one_owner"),
        CheckConstraint("run >= 1", name="run_positive"),
        Index("ix_scans_user_id_created_at", "user_id", "created_at"),
        Index("ix_scans_guest_key_created_at", "guest_key", "created_at"),
    )

    id: Mapped[int] = public_id_pk("scans")
    user_id: Mapped[uuid.UUID | None] = _user_column()
    guest_key: Mapped[str | None] = _guest_column()
    source: Mapped[ScanSource] = mapped_column(string_enum(ScanSource, "source"))
    status: Mapped[ScanStatus] = mapped_column(string_enum(ScanStatus, "status"))
    outcome: Mapped[ScanOutcome | None] = mapped_column(string_enum(ScanOutcome, "outcome"))
    # A stable error code (v2 §26) when the scan failed.
    error_code: Mapped[str | None] = mapped_column(String(32))
    run: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    # The engine that made the insights: `pipeline`, or `demo`, a declared simulation.
    engine: Mapped[str] = mapped_column(String(16))
    sensitive: Mapped[bool] = mapped_column(Boolean, server_default=false())
    sensitive_categories: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'")
    )
    image_width: Mapped[int | None] = mapped_column(Integer)
    image_height: Mapped[int | None] = mapped_column(Integer)
    scene: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # What the learner pointed at: `{"entity_id": ...}` or `{"box": {...}, "label": ...}`.
    focus: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    clarification_question: Mapped[str | None] = mapped_column(Text)
    clarification_answer: Mapped[str | None] = mapped_column(Text)
    # Hadith the engine wanted and that wait for an editor's ruling: [{collection, number}].
    awaiting_ruling: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Insight(Base):
    """
    One insight, its evidence by reference, its explanation and what the learner did with it.

    The verse and the hadith are kept as references (surah and ayah, collection
    and number) with why they were chosen; their text is read from the store by
    reference every time the insight is shown. A hadith without an editor's
    eligible ruling is kept but not shown (decision 18).
    """

    __tablename__ = "insights"
    __table_args__ = (
        CheckConstraint(ONE_OWNER, name="one_owner"),
        CheckConstraint(
            "(origin = 'scan') = (scan_id IS NOT NULL)", name="scan_insight_has_a_scan"
        ),
        CheckConstraint(
            "(origin = 'tutorial') = (tutorial_slug IS NOT NULL)",
            name="tutorial_insight_has_a_slug",
        ),
        CheckConstraint(
            "(quran_surah IS NULL) = (quran_ayah IS NULL)", name="quran_reference_whole"
        ),
        CheckConstraint(
            "(hadith_collection IS NULL) = (hadith_number IS NULL)",
            name="hadith_reference_whole",
        ),
        # A guest's insight is never public: publishing needs an account (decision 25).
        CheckConstraint("published_at IS NULL OR user_id IS NOT NULL", name="public_has_account"),
        Index("ix_insights_scan_id", "scan_id"),
        Index(
            "ix_insights_published_at",
            "published_at",
            postgresql_where=text("published_at IS NOT NULL"),
        ),
        Index("ix_insights_user_id_completed_at", "user_id", "completed_at"),
        Index("ix_insights_guest_key_completed_at", "guest_key", "completed_at"),
        Index(
            "uq_insights_user_tutorial",
            "user_id",
            "tutorial_scene",
            "tutorial_slug",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL AND tutorial_slug IS NOT NULL"),
        ),
        Index(
            "uq_insights_guest_tutorial",
            "guest_key",
            "tutorial_scene",
            "tutorial_slug",
            unique=True,
            postgresql_where=text("guest_key IS NOT NULL AND tutorial_slug IS NOT NULL"),
        ),
    )

    id: Mapped[int] = public_id_pk("insights")
    user_id: Mapped[uuid.UUID | None] = _user_column()
    guest_key: Mapped[str | None] = _guest_column()
    scan_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("scans.id", ondelete="CASCADE")
    )
    origin: Mapped[InsightOrigin] = mapped_column(string_enum(InsightOrigin, "origin"))
    # The prepared scene and insight a tutorial copy came from, with the data version.
    tutorial_scene: Mapped[str | None] = mapped_column(String(64))
    tutorial_slug: Mapped[str | None] = mapped_column(String(64))
    run: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    position: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    # `pipeline`, `demo` (a declared simulation) or `prepared` (a reviewed tutorial insight).
    engine: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(Text)
    glimpse: Mapped[str] = mapped_column(Text)
    entity_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    action_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    # A box as ratios of the photo: {x, y, width, height}.
    anchor: Mapped[dict[str, float] | None] = mapped_column(JSONB)
    relation: Mapped[str] = mapped_column(String(32))
    quran_surah: Mapped[int | None] = mapped_column(SmallInteger)
    quran_ayah: Mapped[int | None] = mapped_column(SmallInteger)
    # Why the verse was chosen: relation, scores, what it matched on.
    quran_evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    hadith_collection: Mapped[str | None] = mapped_column(String(32))
    hadith_number: Mapped[str | None] = mapped_column(String(32))
    hadith_evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # The platform's own explanation («شرح تبصرة»), «لماذا ظهر هذا؟» and the small step.
    explanation: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    why: Mapped[dict[str, Any]] = mapped_column(JSONB)
    small_step: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    learning_unit_id: Mapped[str | None] = mapped_column(String(16))
    learning_path_version: Mapped[str | None] = mapped_column(String(64))
    action_state: Mapped[ActionState | None] = mapped_column(
        string_enum(ActionState, "action_state")
    )
    action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # «تمّ»: the learner completed the insight. Completion, never mastery.
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    place_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("world_places.id", ondelete="SET NULL")
    )
    # Public while `published_at` is set: the owner's own act, cleared again on withdrawal.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The last time the owner took it down; kept for the owner's history, never public.
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()


class ChatMessage(Base):
    """
    One question about an insight and its answer.

    The idempotency key makes a retry, a refresh or a double send the same
    message: it is answered once and counted once.
    """

    __tablename__ = "insight_chat_messages"
    __table_args__ = (
        UniqueConstraint(
            "insight_id", "idempotency_key", name="uq_insight_chat_messages_idempotency_key"
        ),
        CheckConstraint("level IS NULL OR level IN ('a', 'b', 'c', 'd')", name="level"),
        Index("ix_insight_chat_messages_insight_id", "insight_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    insight_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("insights.id", ondelete="CASCADE")
    )
    idempotency_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[ChatStatus] = mapped_column(string_enum(ChatStatus, "status"))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    # The content level of v2 §12: a, b, c or d.
    level: Mapped[str | None] = mapped_column(String(1))
    # `answer`, `referral` (level d) or `new_search` (a new text was asked for).
    kind: Mapped[str | None] = mapped_column(String(16))
    # The evidence ids (`quran:30:50`, `hadith:bukhari:1032`) shown when the answer was written;
    # null on an answer written before they were kept, which is never shown again.
    evidence_ids: Mapped[list[str] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_column()
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
