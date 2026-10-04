"""Server-side sessions and the short-lived state of a Google sign-in."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, created_at_column, uuid_pk

TOKEN_HASH_BYTES = 32


class Session(Base):
    """
    A signed-in browser.

    The cookie carries a random 256-bit token; only its SHA-256 hash is stored,
    so a copy of this table cannot be replayed as a cookie. The IP address is
    kept as a keyed hash, never as the address.
    """

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(f"octet_length(token_hash) = {TOKEN_HASH_BYTES}", name="token_hash_length"),
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = created_at_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(256))


class OAuthState(Base):
    """
    A Google sign-in in flight: what the callback needs to finish it.

    The row is deleted when the callback reads it, so a state works once. The
    `binder_hash` ties it to the browser that started the flow (a cookie), so a
    callback link an attacker obtained cannot sign a victim into the attacker's
    account.
    """

    __tablename__ = "oauth_states"
    __table_args__ = (Index("ix_oauth_states_expires_at", "expires_at"),)

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    binder_hash: Mapped[str] = mapped_column(String(64))
    code_verifier: Mapped[str] = mapped_column(String(128))
    nonce: Mapped[str] = mapped_column(String(64))
    # Where in the web app to send the user afterwards: a path, never a full URL.
    next_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
