"""
Tokens mailed to an address: e-mail verification and password reset.

A token is 256 random bits in a link. Only its SHA-256 hash is stored, so read
access to the table does not give working links, and a token is never logged.
It works once and until it expires. Asking for a new one cancels the earlier
ones of the same kind, so two inboxes never hold two working links.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock, security
from src.config import Settings
from src.models.email_token import EmailToken, TokenPurpose
from src.models.user import User


def lifetime(settings: Settings, purpose: TokenPurpose) -> timedelta:
    """How long a token of this purpose stays valid."""
    if purpose == TokenPurpose.VERIFY_EMAIL:
        return timedelta(hours=settings.email_verification_expire_hours)
    return timedelta(minutes=settings.password_reset_expire_minutes)


async def cancel_unused(db: AsyncSession, user_id: uuid.UUID, purpose: TokenPurpose) -> None:
    """Make every unused token of this purpose for this user stop working."""
    await db.execute(
        update(EmailToken)
        .where(
            EmailToken.user_id == user_id,
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
        )
        .values(used_at=clock.utcnow())
    )


async def issue(db: AsyncSession, settings: Settings, user: User, purpose: TokenPurpose) -> str:
    """Create a token for a user and return it; it is not recoverable afterwards."""
    now = clock.utcnow()
    # Expired tokens are useless: delete them as new ones are made.
    await db.execute(delete(EmailToken).where(EmailToken.expires_at < now))
    await cancel_unused(db, user.id, purpose)
    token = security.new_token()
    db.add(
        EmailToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=security.hash_token(token),
            email=user.email,
            expires_at=now + lifetime(settings, purpose),
        )
    )
    await db.flush()
    return token


async def redeem(db: AsyncSession, token: str, purpose: TokenPurpose) -> User | None:
    """
    Spend a token and return the account it belongs to, or None for any bad one.

    Unknown, expired, already used, of another purpose, issued for an address
    the account no longer has, or for an account that cannot sign in: all give
    None, so the answer says nothing about which. The claim is one UPDATE that
    only the first of two racing requests can win.
    """
    now = clock.utcnow()
    claimed = (
        await db.execute(
            update(EmailToken)
            .where(
                EmailToken.token_hash == security.hash_token(token),
                EmailToken.purpose == purpose,
                EmailToken.used_at.is_(None),
                EmailToken.expires_at > now,
            )
            .values(used_at=now)
            .returning(EmailToken.user_id, EmailToken.email)
        )
    ).first()
    if claimed is None:
        return None
    user = await db.get(User, claimed.user_id)
    usable = (
        user is not None
        and user.is_active
        and user.deleted_at is None
        and user.email.lower() == claimed.email.lower()
    )
    return user if usable else None
