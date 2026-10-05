"""Accounts: the user and the external identities linked to it."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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

# A public handle: three to thirty letters (Latin or Arabic, no marks), digits and
# underscores, starting with a letter. The same text is the database constraint, so a
# handle the API accepts is one the database accepts. Arabic range: ء to غ and ف to ي,
# which leaves out the tatweel (U+0640) and every diacritic.
HANDLE_PATTERN = r"^[A-Za-z\u0621-\u063A\u0641-\u064A][A-Za-z0-9_\u0621-\u063A\u0641-\u064A]{2,29}$"
HANDLE_MAX = 30
PUBLIC_NAME_MAX = 40


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
    __table_args__ = (
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
        # Two spellings of one handle are never two accounts.
        Index("uq_users_handle_lower", text("lower(handle)"), unique=True),
        CheckConstraint(f"handle ~ '{HANDLE_PATTERN}'", name="handle_format"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(60))
    # The public identity of an account that publishes, chosen on purpose and never
    # derived from the account's own name, which may be a real or a Google name.
    # Both stay empty until the person picks them; nothing is public without them.
    handle: Mapped[str | None] = mapped_column(String(HANDLE_MAX))
    # Kept for the accounts that chose one before decision 63; no response reads it any more.
    public_name: Mapped[str | None] = mapped_column(String(PUBLIC_NAME_MAX))
    # Mirror of the latest `public_full_name` consent row: while true, `display_name` (the real
    # full name) is shown beside the handle; otherwise only the handle is (decision 63).
    public_full_name: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
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
