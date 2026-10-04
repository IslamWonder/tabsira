"""
The learner's world (v2 §16): places that the fog leaves, the threads between them, the treasures.

The map itself is data (`data/world/regions-<version>.json`): one region per
domain of the learning path, at a fixed position. A place exists for an owner
once an insight of its region was completed; it is created once and reused. A
relation joins two places only when something recorded joins them: two
insights completed from the same scene, or a unit of one region that the
learning path names as a prerequisite of a unit of the other. Nothing is drawn
that was not recorded.

A treasure (v2 §17) is prepared when an insight is completed, from verified
candidates only, and stays hidden until the rule of `src/services/treasure.py`
says the learner has come back.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, created_at_column, string_enum, uuid_pk
from src.models.scan import GUEST_KEY_LENGTH, ONE_OWNER


class RelationReason(StrEnum):
    # Both places hold an insight completed from the same scene.
    SAME_SCENE = "same_scene"
    # The learning path names a unit of one place as a prerequisite of a unit of the other.
    PREREQUISITE = "prerequisite"


class TreasureKind(StrEnum):
    # Another verified text of the same unit, of the same weight.
    ALTERNATIVE = "alternative"
    # A unit of the same region that builds on the completed one.
    DEEPER = "deeper"


class WorldPlace(Base):
    """A region of the map where the fog has lifted for one owner."""

    __tablename__ = "world_places"
    __table_args__ = (
        CheckConstraint(ONE_OWNER, name="one_owner"),
        Index(
            "uq_world_places_user_region",
            "user_id",
            "region_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "uq_world_places_guest_region",
            "guest_key",
            "region_id",
            unique=True,
            postgresql_where=text("guest_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    guest_key: Mapped[str | None] = mapped_column(
        String(GUEST_KEY_LENGTH), ForeignKey("guests.key", ondelete="CASCADE")
    )
    region_id: Mapped[str] = mapped_column(String(16))
    # The version of the regions file the place was created with.
    regions_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = created_at_column()
    # The last time the learner opened the place: a return shows its treasure.
    last_visited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorldRelation(Base):
    """A recorded thread between two places of one owner; `place_a_id` sorts before `place_b_id`."""

    __tablename__ = "world_relations"
    __table_args__ = (
        UniqueConstraint(
            "place_a_id", "place_b_id", "reason", name="uq_world_relations_places_reason"
        ),
        CheckConstraint("place_a_id < place_b_id", name="places_ordered"),
        Index("ix_world_relations_place_b_id", "place_b_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    place_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("world_places.id", ondelete="CASCADE"))
    place_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("world_places.id", ondelete="CASCADE"))
    reason: Mapped[RelationReason] = mapped_column(string_enum(RelationReason, "reason"))
    # The two completed insights that recorded the relation.
    insight_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("insights.id", ondelete="CASCADE"))
    insight_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("insights.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = created_at_column()


class Treasure(Base):
    """The hidden treasure of one completed insight: a reference to verified content, or nothing."""

    __tablename__ = "treasures"
    __table_args__ = (
        UniqueConstraint("insight_id", name="uq_treasures_insight_id"),
        CheckConstraint(
            "(quran_surah IS NULL) = (quran_ayah IS NULL)", name="quran_reference_whole"
        ),
        CheckConstraint(
            "(hadith_collection IS NULL) = (hadith_number IS NULL)",
            name="hadith_reference_whole",
        ),
        CheckConstraint(
            "quran_surah IS NOT NULL OR hadith_collection IS NOT NULL", name="has_evidence"
        ),
        Index("ix_treasures_place_id", "place_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    insight_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("insights.id", ondelete="CASCADE"))
    place_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("world_places.id", ondelete="CASCADE"))
    kind: Mapped[TreasureKind] = mapped_column(string_enum(TreasureKind, "kind"))
    quran_surah: Mapped[int | None] = mapped_column(SmallInteger)
    quran_ayah: Mapped[int | None] = mapped_column(SmallInteger)
    hadith_collection: Mapped[str | None] = mapped_column(String(32))
    hadith_number: Mapped[str | None] = mapped_column(String(32))
    # The unit whose verified anchor the treasure is: the completed one, or a deeper one.
    learning_unit_id: Mapped[str] = mapped_column(String(16))
    learning_path_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_at_column()
    revealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
