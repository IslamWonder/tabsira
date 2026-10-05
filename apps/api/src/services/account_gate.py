"""
Who may start a scan and use the chat (decision 63).

A visitor without an account does the rain tutorial and one scan of their own photo; the
next scan asks for an account. An account must have completed its profile before the scan and
the chat. The tutorial never counts: it saves insights without a scan row.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors import AppError, ErrorCode
from src.models import Scan, ScanStatus
from src.owner import Owner
from src.services import profile_service

# Scans a guest key may hold before it must sign up.
GUEST_SCAN_LIMIT = 1


async def require_may_scan(db: AsyncSession, owner: Owner) -> None:
    """
    Refuse a guest that holds its one scan, and an account with no completed profile.

    The guest gets 403 `account_required`, the account 403 `profile_required`. A scan that failed delivered nothing (the queue was down, the photo could not be read), so
    it does not use up the guest's one scan.
    """
    if owner.user_id is not None:
        await profile_service.require_completed(db, owner.user_id)
        return
    held = await db.scalar(
        select(func.count())
        .select_from(Scan)
        .where(Scan.guest_key == owner.guest_key, Scan.status != ScanStatus.FAILED)
    )
    if (held or 0) >= GUEST_SCAN_LIMIT:
        raise AppError(
            ErrorCode.account_required,
            "Create an account to scan again.",
            status_code=403,
        )


async def require_profile(db: AsyncSession, owner: Owner) -> None:
    """Answer 403 `profile_required` for an account with no completed profile; guests pass."""
    if owner.user_id is not None:
        await profile_service.require_completed(db, owner.user_id)
