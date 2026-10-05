"""
Rate limiting kept in PostgreSQL.

There is no Redis. Attempts are rows in `login_attempts`, so every worker and
every process counts against the same totals, and a restart forgets nothing.
An attempt is identified by keyed hashes of its IP address and e-mail address,
never by the addresses. The counted window slides: an attempt stops counting
when it is older than AUTH_ATTEMPT_WINDOW_SECONDS and is deleted soon after.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src import clock
from src.config import Settings
from src.errors import AppError, ErrorCode
from src.models.login_attempt import AttemptKind, LoginAttempt

# Only a sign-in that fails is held against the caller: an address that signs in
# with the right password must not be locked out by its own sessions. Everything
# else (sign-up, the mail-sending routes, the link redemptions) counts every attempt.
# The support form's window, an hour: longer than the sign-in one, so purged by its own cutoff.
SUPPORT_WINDOW_SECONDS = 3600
COUNTS_ONLY_FAILURES = frozenset({AttemptKind.LOGIN})


async def _count(
    db: AsyncSession, kind: AttemptKind, match: ColumnElement[bool], since: object
) -> int:
    conditions = [LoginAttempt.kind == kind, match, LoginAttempt.created_at >= since]
    if kind in COUNTS_ONLY_FAILURES:
        conditions.append(LoginAttempt.succeeded.is_(False))
    total = await db.scalar(select(func.count()).select_from(LoginAttempt).where(*conditions))
    return total or 0


async def _raise_if_over(
    db: AsyncSession,
    settings: Settings,
    kind: AttemptKind,
    *,
    ip_hash: str,
    email_hash: str | None,
    counted_already: int,
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
        # `counted_already` is the caller's own, just-recorded attempt: it must not count
        # against itself.
        if await _count(db, kind, match, since) - counted_already >= limit:
            raise AppError(
                ErrorCode.RATE_LIMITED,
                "Too many attempts. Try again later.",
                status_code=429,
                headers={"Retry-After": str(settings.auth_attempt_window_seconds)},
            )


async def check(
    db: AsyncSession,
    settings: Settings,
    kind: AttemptKind,
    *,
    ip_hash: str,
    email_hash: str | None = None,
) -> None:
    """Raise a 429 when this IP, or this e-mail, has used up its attempts in the window."""
    await _raise_if_over(
        db, settings, kind, ip_hash=ip_hash, email_hash=email_hash, counted_already=0
    )


async def reserve(
    db: AsyncSession,
    settings: Settings,
    kind: AttemptKind,
    *,
    ip_hash: str,
    email_hash: str | None = None,
) -> int:
    """
    Take one attempt before the password is checked, and return its id.

    A slow check (bcrypt) between `check` and `record` lets any number of parallel requests
    all see a count under the limit. Here the attempt is written as a failure and committed
    first, in a short transaction of its own, and only then counted: each parallel request
    sees the others, so no more than the limit gets through. A refused request gives its
    attempt back, since it was never tried. `settle` marks the attempt that succeeded.

    The session must hold nothing else pending: the commit would take it too.
    """
    attempt_id = await _add(db, settings, kind, ip_hash, email_hash, succeeded=False)
    await db.commit()
    try:
        await _raise_if_over(
            db, settings, kind, ip_hash=ip_hash, email_hash=email_hash, counted_already=1
        )
    except AppError:
        await db.execute(delete(LoginAttempt).where(LoginAttempt.id == attempt_id))
        await db.commit()
        raise
    return attempt_id


async def settle(db: AsyncSession, attempt_id: int) -> None:
    """Mark a reserved attempt as one that succeeded, so it stops counting. The caller commits."""
    await db.execute(
        update(LoginAttempt).where(LoginAttempt.id == attempt_id).values(succeeded=True)
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
    await _add(db, settings, kind, ip_hash, email_hash, succeeded=succeeded)


async def _add(
    db: AsyncSession,
    settings: Settings,
    kind: AttemptKind,
    ip_hash: str,
    email_hash: str | None,
    *,
    succeeded: bool,
) -> int:
    """Delete the attempts too old to count, add one, flush, and return its id."""
    now = clock.utcnow()
    await _purge(db, settings, now)
    attempt = LoginAttempt(
        kind=kind, ip_hash=ip_hash, email_hash=email_hash, succeeded=succeeded, created_at=now
    )
    db.add(attempt)
    await db.flush()
    return attempt.id


def _purge_condition(settings: Settings, now: datetime) -> ColumnElement[bool]:
    """Rows older than the window of their own kind: the sign-in one, or the support one."""
    auth_cutoff = now - timedelta(seconds=settings.auth_attempt_window_seconds)
    support_cutoff = now - timedelta(seconds=SUPPORT_WINDOW_SECONDS)
    return or_(
        and_(LoginAttempt.kind != AttemptKind.SUPPORT, LoginAttempt.created_at < auth_cutoff),
        and_(LoginAttempt.kind == AttemptKind.SUPPORT, LoginAttempt.created_at < support_cutoff),
    )


async def _purge(db: AsyncSession, settings: Settings, now: datetime) -> None:
    await db.execute(delete(LoginAttempt).where(_purge_condition(settings, now)))


# `POST /auth/legal/accept` budgets (no setting: a person accepts once or twice in a lifetime).
LEGAL_ACCEPT_PER_IP = 30
LEGAL_ACCEPT_PER_ACCOUNT = 10
LEGAL_ACCEPT_OVERALL = 5000
LEGAL_ACCEPT_WINDOW_SECONDS = 3600


async def reserve_budgets(
    db: AsyncSession,
    settings: Settings,
    kind: AttemptKind,
    *,
    ip_hash: str,
    email_hash: str,
    per_ip: int,
    per_email: int,
    overall: int,
    window_seconds: int,
) -> None:
    """
    Count one attempt before the work is done, or raise a 429 when a limit is used up.

    For routes whose work costs something (a mail to the team): the attempt is counted
    whether or not the work then succeeds, so a failing mail server cannot be used to
    send without limit. Three budgets over `window_seconds`: this IP, this address, and
    everyone together as a ceiling. It flushes; the caller commits before doing the work.
    Two requests in the same instant can both pass the count: a spam bound, not a quota.
    """
    now = clock.utcnow()
    await _purge(db, settings, now)
    since = now - timedelta(seconds=window_seconds)
    budgets: list[tuple[ColumnElement[bool], int]] = [
        (LoginAttempt.ip_hash == ip_hash, per_ip),
        (LoginAttempt.email_hash == email_hash, per_email),
        (LoginAttempt.ip_hash.is_not(None), overall),
    ]
    for match, limit in budgets:
        if await _count(db, kind, match, since) >= limit:
            raise AppError(
                ErrorCode.RATE_LIMITED,
                "Too many messages. Try again later.",
                status_code=429,
                headers={"Retry-After": str(window_seconds)},
            )
    db.add(
        LoginAttempt(
            kind=kind, ip_hash=ip_hash, email_hash=email_hash, succeeded=True, created_at=now
        )
    )
    await db.flush()
