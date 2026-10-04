"""The admin area's access tables: its sessions and the second factor of each admin."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, created_at_column, uuid_pk

TOKEN_HASH_BYTES = 32


class AdminSession(Base):
    """
    A signed-in admin browser.

    Kept apart from `sessions` on purpose: a different cookie (path `/admin`,
    SameSite=Strict), a twelve-hour life, and a view of its own. Like a user session it
    holds only the SHA-256 hash of the cookie's random token, and a keyed hash of the
    address. The CSRF token is derived from the cookie token, so it is stored nowhere.
    """

    __tablename__ = "admin_sessions"
    __table_args__ = (
        CheckConstraint(f"octet_length(token_hash) = {TOKEN_HASH_BYTES}", name="token_hash_length"),
        Index("ix_admin_sessions_user_id", "user_id"),
        Index("ix_admin_sessions_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = created_at_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(256))


class AdminTotp(Base):
    """
    The time-based one-time password of one admin.

    The shared secret is stored encrypted (Fernet, under ADMIN_TOTP_ENCRYPTION_KEY),
    never in the clear: a copy of this table is useless without the key. The recovery
    codes are stored as keyed hashes and each works once. `enabled_at` is empty while
    the enrolment is started but the first code has not been entered; the code is
    required at sign-in only once it is set. `last_used_step` is the 30-second step
    of the last accepted code, so a code cannot be used twice.
    """

    __tablename__ = "admin_totp"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    secret_encrypted: Mapped[str] = mapped_column(Text)
    recovery_hashes: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), server_default=text("'{}'::varchar[]")
    )
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_step: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = created_at_column()
