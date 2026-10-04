"""
The learning path («مسار») and what a learner has done with it.

The path is data, not code. Each release is a **path version** (`tabsira-masar-1.0`
and the ones that follow): its domains and units are rows that carry that version,
so a monthly content release adds a version and changes no code. A learner's state
names the version of the unit it belongs to, because when a unit's meaning changes
its old evidence is not carried over to the new meaning (masar §14, rule 7).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class LearningPathVersion(Base):
    """One release of the learning path; at most one is active."""

    __tablename__ = "learning_path_versions"
    __table_args__ = (
        Index(
            "uq_learning_path_versions_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    path_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(32))
    released_on: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    # The JSON file this version was imported from, and its hash.
    source_file: Mapped[str] = mapped_column(Text)
    source_sha256: Mapped[str] = mapped_column(String(64))
    domain_count: Mapped[int] = mapped_column(Integer)
    unit_count: Mapped[int] = mapped_column(Integer)
    # The six depths (L0 to L5) and the coverage rules, as the version defines them.
    depths: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    coverage: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=false())
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LearningDomain(Base):
    """A domain of the path (T00 to T15 in version 1.0)."""

    __tablename__ = "learning_domains"
    __table_args__ = (
        UniqueConstraint("path_version", "position", name="uq_learning_domains_position"),
        CheckConstraint("position >= 1", name="position_positive"),
    )

    path_version: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("learning_path_versions.path_version", ondelete="CASCADE"),
        primary_key=True,
    )
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    function: Mapped[str] = mapped_column(Text)
    goal: Mapped[str] = mapped_column(Text)
    # The central values and concepts of the domain, as the version lists them.
    concepts: Mapped[list[str]] = mapped_column(ARRAY(Text))


class LearningUnit(Base):
    """
    A unit of a domain: one small, definite thing a learner can come to understand.

    The id is stable and never reused for another meaning. `evidence_refs` and
    `source_anchors` are pointers for retrieval and review (a surah and a verse
    number, a hadith collection and number); they are never the text of a verse or
    a hadith, which is loaded from its own table and shown byte for byte.
    """

    __tablename__ = "learning_units"
    __table_args__ = (
        ForeignKeyConstraint(
            ["path_version", "domain_id"],
            ["learning_domains.path_version", "learning_domains.id"],
            ondelete="CASCADE",
            name="fk_learning_units_domain",
        ),
        UniqueConstraint(
            "path_version", "domain_id", "position", name="uq_learning_units_position"
        ),
        CheckConstraint("position >= 1", name="position_positive"),
        Index("ix_learning_units_domain", "path_version", "domain_id"),
    )

    path_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    domain_id: Mapped[str] = mapped_column(String(16))
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    objectives: Mapped[list[str]] = mapped_column(ARRAY(Text))
    # Units whose meaning is prepared before this one goes deeper; never a lock.
    prerequisites: Mapped[list[str]] = mapped_column(ARRAY(Text))
    depths: Mapped[list[str]] = mapped_column(ARRAY(Text))
    concepts: Mapped[list[str]] = mapped_column(ARRAY(Text))
    evidence_refs: Mapped[list[str]] = mapped_column(ARRAY(Text))
    source_anchors: Mapped[list[str]] = mapped_column(ARRAY(Text))


class LearnerUnitState(Base):
    """
    What one learner has seen, opened and completed of one unit of one path version.

    The owner is an account (`user_id`) or a guest (`guest_key`, an opaque key the
    browser holds), never both. `completed_count` counts completions: the learner
    pressed «تمّ» on an insight of this unit. It is not mastery and never becomes
    a score; understanding is recorded elsewhere, from answers, and only there.
    A row exists once something happened, so its absence means «not seen».
    """

    __tablename__ = "learner_unit_states"
    __table_args__ = (
        ForeignKeyConstraint(
            ["path_version", "unit_id"],
            ["learning_units.path_version", "learning_units.id"],
            name="fk_learner_unit_states_unit",
        ),
        CheckConstraint("num_nonnulls(user_id, guest_key) = 1", name="one_owner"),
        CheckConstraint("char_length(guest_key) >= 16", name="guest_key_length"),
        CheckConstraint(
            "seen_count >= 0 AND opened_count >= 0 AND completed_count >= 0",
            name="counts_not_negative",
        ),
        Index(
            "uq_learner_unit_states_user",
            "user_id",
            "path_version",
            "unit_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "uq_learner_unit_states_guest",
            "guest_key",
            "path_version",
            "unit_id",
            unique=True,
            postgresql_where=text("guest_key IS NOT NULL"),
        ),
        Index("ix_learner_unit_states_unit", "path_version", "unit_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # TODO(accounts): a foreign key to users.id with ON DELETE CASCADE, once the accounts
    # migration is in this chain, so deleting an account deletes its learning state.
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    guest_key: Mapped[str | None] = mapped_column(String(64))
    path_version: Mapped[str] = mapped_column(String(64))
    unit_id: Mapped[str] = mapped_column(String(16))
    seen_count: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), comment="Times an insight of this unit was shown."
    )
    opened_count: Mapped[int] = mapped_column(
        Integer,
        server_default=text("0"),
        comment="Times the learner opened it or one of its sources.",
    )
    completed_count: Mapped[int] = mapped_column(
        Integer,
        server_default=text("0"),
        comment="Times the learner pressed done on an insight of this unit: completion, never mastery.",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
