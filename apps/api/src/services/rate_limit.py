"""
Rate limiting kept in PostgreSQL.

There is no Redis. Attempts are rows in `login_attempts`, so every worker and
every process counts against the same totals, and a restart forgets nothing.
An attempt is identified by keyed hashes of its IP address and e-mail address,
never by the addresses. The counted window slides: an attempt stops counting
when it is older than AUTH_ATTEMPT_WINDOW_SECONDS and is deleted soon after.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src import clock
from src.config import Settings
from src.errors import AppError, ErrorCode
from src.models.login_attempt import AttemptKind, LoginAttempt

# Only a sign-in that fails is held against the caller: an address that signs in
# with the right password must not be locked out by its own sessions. Everything
# else (sign-up, the mail-sending routes, the link redemptions) counts every attempt.
COUNTS_ONLY_FAILURES = frozenset({AttemptKind.LOGIN})


async def _count(
    db: AsyncSession, kind: AttemptKind, match: ColumnElement[bool], since: object
) -> int:
    conditions = [LoginAttempt.kind == kind, match, LoginAttempt.created_at >= since]
    if kind in COUNTS_ONLY_FAILURES:
        conditions.append(LoginAttempt.succeeded.is_(False))
    total = await db.scalar(select(func.count()).select_from(LoginAttempt).where(*conditions))
    return total or 0


async def check(
    db: AsyncSession,
    settings: Settings,
    kind: AttemptKind,
    *,
    ip_hash: str,
    email_hash: str | None = None,
) -> None:
    """Raise a 429 when this IP, or this e-mail, has used up its attempts in the window."""
    window = timedelta(seconds=settings.auth_attempt_window_seconds)
    since = clock.utcnow() - window
    limits: list[tuple[ColumnElement[bool], int]] = [
        (LoginAttempt.ip_hash == ip_hash, settings.auth_max_attempts_per_ip)
    ]
    if email_hash is not None:
        limits.append((LoginAttempt.email_hash == email_hash, settings.auth_max_attempts_per_email))
    for match, limit in limits:
        if await _count(db, kind, match, since) >= limit:
            raise AppError(
                ErrorCode.RATE_LIMITED,
                "Too many attempts. Try again later.",
                status_code=429,
                headers={"Retry-After": str(settings.auth_attempt_window_seconds)},
            )


async def record(
    db: AsyncSession,
    settings: Settings,
    kind: AttemptKind,
    *,
    ip_hash: str,
    email_hash: str | None = None,
    succeeded: bool,
) -> None:
    """
    Remember one attempt, and delete the ones too old to count.

    It only flushes: the caller commits, and must do so even when it goes on to
    refuse the request, or the attempt is lost with the rolled-back transaction.
    """
    now = clock.utcnow()
    cutoff = now - timedelta(seconds=settings.auth_attempt_window_seconds)
    await db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < cutoff))
    db.add(
        LoginAttempt(
            kind=kind, ip_hash=ip_hash, email_hash=email_hash, succeeded=succeeded, created_at=now
        )
    )
    await db.flush()
