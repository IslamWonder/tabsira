"""
Who may start a scan and use the chat (decision 64).

A visitor without an account does the rain tutorial and one scan of their own photo; the
next scan asks for an account. An account must have completed its profile before the scan and
the chat. The tutorial never counts: it saves insights without a scan row. Once an account holds
an insight of its own, the prepared rain example is no longer offered to it.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors import AppError, ErrorCode
from src.models import Guest, Insight, InsightOrigin, Scan, ScanStatus
from src.services import profile_service

if TYPE_CHECKING:
    # Only for the annotations: `src.owner` imports the request dependencies, which
    # import the services, which import this module. The scan worker enters that
    # ring from `src.owner` and a runtime import here breaks it.
    from src.owner import Owner

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
    # Two parallel first scans would both count none: the guest's row is locked until the scan
    # that follows is committed, so the second request counts after the first one is there.
    await db.scalar(select(Guest.key).where(Guest.key == owner.guest_key).with_for_update())
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


async def require_profile(db: AsyncSession, owner: Owner | None) -> None:
    """Answer 403 `profile_required` for an account with no completed profile; guests pass."""
    if owner is not None and owner.user_id is not None:
        await profile_service.require_completed(db, owner.user_id)


def require_account_for_chat(owner: Owner | None, insight: Insight) -> None:
    """Answer 403 `account_required` for a guest opening the chat of an insight of its own scan."""
    if owner is not None and owner.user_id is None and insight.origin is InsightOrigin.SCAN:
        raise AppError(
            ErrorCode.account_required,
            "Create an account to talk about your own scan.",
            status_code=403,
        )


async def has_own_insight(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Whether the account holds an insight of its own scan, not a tutorial copy."""
    found = await db.scalar(
        select(Insight.id)
        .where(Insight.user_id == user_id, Insight.origin == InsightOrigin.SCAN)
        .limit(1)
    )
    return found is not None


async def require_tutorial_open(db: AsyncSession, owner: Owner) -> None:
    """Answer 403 `tutorial_closed` for an account that holds an insight of its own."""
    if owner.user_id is not None and await has_own_insight(db, owner.user_id):
        raise AppError(
            ErrorCode.tutorial_closed,
            "The prepared example is for a first visit; continue with your own photos.",
            status_code=403,
        )
