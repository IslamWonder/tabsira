"""Single-use tokens mailed to an address: e-mail verification and password reset."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, created_at_column, string_enum, uuid_pk
from src.models.session import TOKEN_HASH_BYTES


class TokenPurpose(StrEnum):
    VERIFY_EMAIL = "verify_email"
    PASSWORD_RESET = "reset_password"  # noqa: S105  # nosec B105 - a purpose name, not a password


class EmailToken(Base):
    """
    A link token that was mailed to a user.

    Like a session token it is stored only as its SHA-256 hash, so a copy of this
    table cannot be turned into working links. It works once (`used_at`), until
    `expires_at`, and a verification token is bound to the address it was sent
    to, so changing the address kills the links still sitting in the old inbox.
    """

    __tablename__ = "email_tokens"
    __table_args__ = (
        CheckConstraint(f"octet_length(token_hash) = {TOKEN_HASH_BYTES}", name="token_hash_length"),
        Index("ix_email_tokens_user_id_purpose", "user_id", "purpose"),
        Index("ix_email_tokens_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[TokenPurpose] = mapped_column(string_enum(TokenPurpose, "purpose"))
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    # The address the mail went to, for the purposes that are bound to one.
    email: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = created_at_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
