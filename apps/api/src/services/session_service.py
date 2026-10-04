"""
Server-side sessions and the cookie that carries them.

The cookie holds a random 256-bit token. The database holds only its SHA-256
hash, with the user, the lifetime and a keyed hash of the IP. A request is
signed in when its cookie hashes to an unexpired row of an active account.
Signing out deletes the row, so a stolen cookie dies with it: there is nothing
to wait out, as there would be with a signed token.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock, security
from src.config import Settings
from src.models.session import Session
from src.models.user import User
from src.services import admin_session_service

# `last_seen_at` is written at most this often, so reading does not mean writing.
TOUCH_INTERVAL = timedelta(minutes=5)
USER_AGENT_MAX = 256
# A cookie longer than any real token is not hashed at all.
TOKEN_MAX = 128


def cookie_token(request: Request, settings: Settings) -> str | None:
    """Return the session token the request's cookie carries, if it looks like one."""
    token = request.cookies.get(settings.session_cookie_name)
    return token if token and len(token) <= TOKEN_MAX else None


def set_cookie(response: Response, settings: Settings, token: str) -> None:
    """
    Attach the session cookie: httpOnly, Secure, SameSite=Lax.

    The domain is shared by the web and api subdomains, so the browser sends the
    cookie to the API from pages of the web app. Lax keeps it off cross-site
    POSTs; the Origin check covers the sibling subdomains Lax does not.
    """
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=int(settings.session_ttl.total_seconds()),
        path="/",
        domain=settings.session_cookie_domain or None,
        secure=True,
        httponly=True,
        samesite="lax",
    )


def clear_cookie(response: Response, settings: Settings) -> None:
    """Tell the browser to drop the session cookie."""
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        domain=settings.session_cookie_domain or None,
        secure=True,
        httponly=True,
        samesite="lax",
    )


async def create(
    db: AsyncSession,
    settings: Settings,
    *,
    user_id: uuid.UUID,
    ip_hash: str,
    user_agent: str | None,
) -> str:
    """Open a session for a user and return its token, which exists nowhere else."""
    now = clock.utcnow()
    # Expired rows are deleted as new ones arrive; there is no scheduled job.
    await db.execute(delete(Session).where(Session.expires_at < now))
    token = security.new_token()
    db.add(
        Session(
            token_hash=security.hash_token(token),
            user_id=user_id,
            created_at=now,
            expires_at=now + settings.session_ttl,
            last_seen_at=now,
            ip_hash=ip_hash,
            user_agent=(user_agent or None) and user_agent[:USER_AGENT_MAX],
        )
    )
    await db.flush()
    return token


async def start_for_request(
    db: AsyncSession,
    settings: Settings,
    request: Request,
    *,
    user_id: uuid.UUID,
    ip_hash: str,
) -> str:
    """
    Sign a user in from a request: end the session the browser held, open a new one.

    A fresh token at every sign-in means a token planted in the browser before
    it is never the one that ends up signed in (session fixation).
    """
    previous = cookie_token(request, settings)
    if previous is not None:
        await revoke(db, previous)
    return await create(
        db,
        settings,
        user_id=user_id,
        ip_hash=ip_hash,
        user_agent=request.headers.get("user-agent"),
    )


async def find(db: AsyncSession, token: str) -> tuple[Session, User] | None:
    """Return the live session and its account for a token, or None."""
    row = (
        await db.execute(
            select(Session, User)
            .join(User, User.id == Session.user_id)
            .where(
                Session.token_hash == security.hash_token(token),
                Session.expires_at > clock.utcnow(),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
    ).first()
    return None if row is None else (row[0], row[1])


async def touch(db: AsyncSession, session: Session) -> bool:
    """Record that the session was just used, at most once per `TOUCH_INTERVAL`; say if it wrote."""
    now: datetime = clock.utcnow()
    if now - session.last_seen_at < TOUCH_INTERVAL:
        return False
    session.last_seen_at = now
    await db.flush()
    return True


async def revoke(db: AsyncSession, token: str) -> None:
    """End the session a token belongs to; unknown tokens are ignored."""
    await db.execute(delete(Session).where(Session.token_hash == security.hash_token(token)))


async def revoke_all(
    db: AsyncSession, user_id: uuid.UUID, *, keep_token: str | None = None
) -> None:
    """End every session of a user, except the one named by `keep_token`."""
    condition = [Session.user_id == user_id]
    if keep_token is not None:
        condition.append(Session.token_hash != security.hash_token(keep_token))
    await db.execute(delete(Session).where(*condition))


async def revoke_every_session(
    db: AsyncSession, user_id: uuid.UUID, *, keep_token: str | None = None
) -> None:
    """
    End the user's ordinary sessions (but `keep_token`) and every admin session.

    For a change of credential: a password reset, or the removal of a password. An admin
    session is never kept: whoever holds one must sign in again with the new credential.
    """
    await revoke_all(db, user_id, keep_token=keep_token)
    await admin_session_service.revoke_all(db, user_id)
