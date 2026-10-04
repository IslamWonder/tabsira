"""
The admin area's sessions and the cookie that carries them.

Modelled on `session_service`, with the differences an admin cookie needs: its own
name, path `/admin` and SameSite=Strict, a twelve-hour life that is never extended, and
a lookup that insists the account is still an active admin. Every admin request goes
through `find`, so removing `is_admin`, deactivating or deleting an account ends its
admin access at once, whatever the cookie says.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import Request, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock, security
from src.config import Settings
from src.models.admin_access import AdminSession
from src.models.user import User

ADMIN_COOKIE_NAME = "__Secure-tabsira_admin"
# The cookie is sent to the admin area and nowhere else, and to no other host.
ADMIN_COOKIE_PATH = "/admin"
ADMIN_SESSION_TTL = timedelta(hours=12)
# `last_seen_at` is written at most this often, so reading does not mean writing.
TOUCH_INTERVAL = timedelta(minutes=5)
USER_AGENT_MAX = 256
# A cookie longer than any real token is not hashed at all.
TOKEN_MAX = 128
CSRF_PURPOSE = "admin-csrf"


def cookie_token(request: Request) -> str | None:
    """Return the token the request's admin cookie carries, if it looks like one."""
    token = request.cookies.get(ADMIN_COOKIE_NAME)
    return token if token and len(token) <= TOKEN_MAX else None


def set_cookie(response: Response, token: str) -> None:
    """
    Attach the admin cookie: httpOnly, Secure, SameSite=Strict, path /admin, twelve hours.

    There is no Domain attribute, so it belongs to the API's own host and is not shared
    with the web app's subdomains the way the user cookie is.
    """
    response.set_cookie(
        ADMIN_COOKIE_NAME,
        token,
        max_age=int(ADMIN_SESSION_TTL.total_seconds()),
        path=ADMIN_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="strict",
    )


def clear_cookie(response: Response) -> None:
    """Tell the browser to drop the admin cookie."""
    response.delete_cookie(
        ADMIN_COOKIE_NAME,
        path=ADMIN_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="strict",
    )


def csrf_token_for(settings: Settings, token: str) -> str:
    """
    Return the CSRF token of the session whose cookie holds `token`.

    A keyed hash of the cookie's token, so nothing is stored and a page of another site
    cannot know it: the cookie that it derives from is httpOnly.
    """
    return security.keyed_hash(settings.hash_key, CSRF_PURPOSE, token)


async def create(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    ip_hash: str,
    user_agent: str | None,
) -> str:
    """Open an admin session and return its token, which exists nowhere else."""
    now = clock.utcnow()
    # Expired rows are deleted as new ones arrive; there is no scheduled job.
    await db.execute(delete(AdminSession).where(AdminSession.expires_at < now))
    token = security.new_token()
    db.add(
        AdminSession(
            token_hash=security.hash_token(token),
            user_id=user_id,
            created_at=now,
            expires_at=now + ADMIN_SESSION_TTL,
            last_seen_at=now,
            ip_hash=ip_hash,
            user_agent=(user_agent or None) and user_agent[:USER_AGENT_MAX],
        )
    )
    await db.flush()
    return token


async def find(db: AsyncSession, token: str) -> tuple[AdminSession, User] | None:
    """Return the live session and its account for a token, or None; the account must still be an admin."""
    row = (
        await db.execute(
            select(AdminSession, User)
            .join(User, User.id == AdminSession.user_id)
            .where(
                AdminSession.token_hash == security.hash_token(token),
                AdminSession.expires_at > clock.utcnow(),
                User.is_admin.is_(True),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
    ).first()
    return None if row is None else (row[0], row[1])


async def touch(db: AsyncSession, session: AdminSession) -> bool:
    """Record that the session was just used, at most once per `TOUCH_INTERVAL`; say if it wrote."""
    now = clock.utcnow()
    if now - session.last_seen_at < TOUCH_INTERVAL:
        return False
    session.last_seen_at = now
    await db.flush()
    return True


async def revoke(db: AsyncSession, token: str) -> None:
    """End the session a token belongs to; unknown tokens are ignored."""
    await db.execute(
        delete(AdminSession).where(AdminSession.token_hash == security.hash_token(token))
    )


async def revoke_all(db: AsyncSession, user_id: uuid.UUID) -> None:
    """End every admin session of a user."""
    await db.execute(delete(AdminSession).where(AdminSession.user_id == user_id))
