"""Accounts: the user and the external identities linked to it."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    false,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, created_at_column, uuid_pk

GOOGLE = "google"


class User(Base):
    """
    An account.

    The address is kept lower-cased and the unique index is on `lower(email)`, so
    two spellings of one address can never be two accounts. `password_hash` is
    empty for an account that signs in with Google only. Deleting an account
    deletes the row: everything a user owns references it with ON DELETE CASCADE.
    """

    # Read the database-set `updated_at` back with the UPDATE: no lazy load in async code.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __tablename__ = "users"
    __table_args__ = (Index("uq_users_email_lower", text("lower(email)"), unique=True),)

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(60))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # Set when the address is proven: by Google, which verified it, or later by a mailed link.
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # A soft-deleted account: it can no longer sign in and no session of it is valid.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OAuthAccount(Base):
    """An identity at an external provider, linked to one user."""

    __tablename__ = "oauth_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_oauth_accounts_provider_subject"),
        Index("ix_oauth_accounts_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(32))
    # The provider's stable id of the person (Google's `sub`), never the e-mail address.
    subject: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = created_at_column()
