"""
The optional profile: what a user chose to tell, and their settings.

Every unanswered answer is `unknown` (or an empty list). Nothing here is ever
inferred from a photo, a name, a place or behaviour, and there is no birth
date: the age is a range the user picks. The religious background, the gender
and the age range are private: only their owner reads them (see docs/PRIVACY.md).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    Uuid,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, string_enum


class Goal(StrEnum):
    """Why the user is here (master prompt v2, section 5); several may be chosen."""

    DISCOVER_ISLAM = "discover_islam"  # التعرّف إلى الإسلام
    REFLECTION = "reflection"  # التفكر
    LEARN_QURAN_SUNNAH = "learn_quran_sunnah"  # تعلّم القرآن والسنة
    LIVE_VALUES = "live_values"  # العمل بالقيم
    RESEARCH = "research"  # البحث
    TEACHING = "teaching"  # التعليم
    CURIOSITY = "curiosity"  # الفضول والاستكشاف


class KnowledgeLevel(StrEnum):
    NEW = "new"
    GENERAL = "general"
    ADVANCED = "advanced"
    SPECIALIST = "specialist"
    UNKNOWN = "unknown"


class AgeRange(StrEnum):
    UNDER_13 = "under_13"
    FROM_13_TO_17 = "13_17"
    FROM_18_TO_24 = "18_24"
    FROM_25_TO_39 = "25_39"
    FROM_40_TO_59 = "40_59"
    SIXTY_PLUS = "60_plus"
    UNKNOWN = "unknown"


class ReligiousBackground(StrEnum):
    MUSLIM = "muslim"
    NON_MUSLIM = "non_muslim"
    UNKNOWN = "unknown"


class Gender(StrEnum):
    MAN = "man"
    WOMAN = "woman"
    UNKNOWN = "unknown"


class Theme(StrEnum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


class ReducedMotion(StrEnum):
    """Whether decorative motion is reduced: `system` follows the device setting."""

    SYSTEM = "system"
    ON = "on"
    OFF = "off"


_GOALS_SQL = "goals <@ ARRAY[" + ", ".join(f"'{goal.value}'" for goal in Goal) + "]::text[]"


class Profile(Base):
    """One per user; created with the account, deleted with it."""

    # Read the database-set `updated_at` back with the UPDATE: no lazy load in async code.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __tablename__ = "profiles"
    __table_args__ = (CheckConstraint(_GOALS_SQL, name="goals_known"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    goals: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'::text[]")
    )
    knowledge_level: Mapped[KnowledgeLevel] = mapped_column(
        string_enum(KnowledgeLevel, "knowledge_level"),
        default=KnowledgeLevel.UNKNOWN,
        server_default=KnowledgeLevel.UNKNOWN.value,
    )
    age_range: Mapped[AgeRange] = mapped_column(
        string_enum(AgeRange, "age_range"),
        default=AgeRange.UNKNOWN,
        server_default=AgeRange.UNKNOWN.value,
    )
    religious_background: Mapped[ReligiousBackground] = mapped_column(
        string_enum(ReligiousBackground, "religious_background"),
        default=ReligiousBackground.UNKNOWN,
        server_default=ReligiousBackground.UNKNOWN.value,
    )
    gender: Mapped[Gender] = mapped_column(
        string_enum(Gender, "gender"),
        default=Gender.UNKNOWN,
        server_default=Gender.UNKNOWN.value,
    )
    language: Mapped[str] = mapped_column(String(35), default="ar", server_default="ar")
    # The two switches the user can turn off at any time (master prompt v2, section 5).
    personalization_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    # Off until the user says yes once, plainly; withdrawable. Mirrors the latest
    # `photo_storage` row of the consents table.
    photo_storage_consent: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    theme: Mapped[Theme] = mapped_column(
        string_enum(Theme, "theme"), default=Theme.SYSTEM, server_default=Theme.SYSTEM.value
    )
    reduced_motion: Mapped[ReducedMotion] = mapped_column(
        string_enum(ReducedMotion, "reduced_motion"),
        default=ReducedMotion.SYSTEM,
        server_default=ReducedMotion.SYSTEM.value,
    )
    sound_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Version of the latest consent text the user answered.
    consent_version: Mapped[str | None] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
