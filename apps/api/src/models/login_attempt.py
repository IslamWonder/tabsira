"""Attempts at sign-in, sign-up and the mail-sending routes, kept only long enough to rate limit them."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, Identity, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, created_at_column, string_enum


class AttemptKind(StrEnum):
    LOGIN = "login"
    SIGNUP = "signup"
    GOOGLE_START = "google_start"
    RESEND_VERIFICATION = "resend_verification"
    PASSWORD_FORGOT = "forgot_password"  # noqa: S105  # nosec B105 - an attempt kind, not a password
    SUPPORT = "support"
    EMAIL_TOKEN = "email_token"  # noqa: S105  # nosec B105 - redeeming a verification or reset link


class LoginAttempt(Base):
    """
    One attempt, identified only by keyed hashes of its IP address and e-mail.

    Rows older than the rate-limit window serve no purpose and are deleted as new
    attempts arrive; there is no scheduled job.
    """

    __tablename__ = "login_attempts"
    __table_args__ = (
        Index("ix_login_attempts_ip_hash_created_at", "ip_hash", "created_at"),
        Index("ix_login_attempts_email_hash_created_at", "email_hash", "created_at"),
        Index("ix_login_attempts_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[AttemptKind] = mapped_column(string_enum(AttemptKind, "kind"))
    ip_hash: Mapped[str] = mapped_column(String(64))
    email_hash: Mapped[str | None] = mapped_column(String(64))
    succeeded: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = created_at_column()
