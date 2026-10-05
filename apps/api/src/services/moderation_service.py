"""
What happens to a post or a comment after it is written, and the log that says so.

Two kinds of decision reach here. The automatic guard's verdict settles an item the moment it
is submitted: published, refused with a reason, or held for a person. A moderator's decision
(from the admin area, which calls these functions) approves a held or refused item, refuses a
held one, or removes a published one. Every decision is one row in the moderation log, with
its source and a reason code, and any open reports on the item are closed with it. The author
is told the outcome by the status and reason their own copy of the item carries.

A moderator never edits an author's words and never touches scripture; the only things that
change are the item's state and the log.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock
from src.errors import AppError, ErrorCode
from src.messages import messages_for
from src.models.atlas import MapEntry, MapEntrySponsorship, MapEntryStatus
from src.models.moderation import (
    ModerationAction,
    ModerationActionKind,
    ModerationSource,
    ModerationTarget,
)
from src.models.social import (
    Comment,
    CommentStatus,
    InsightPublication,
    Post,
    PostStatus,
    RemovalSource,
    Report,
    ReportStatus,
    ReportTarget,
)
from src.services import photo_service
from src.services.moderation_guard import GuardVerdict, Outcome
from src.storage.photos import PhotoStore

type Item = Post | Comment | MapEntry

HELD_BY_REPORTS = "reported"


def _target(item: Item) -> ModerationTarget:
    if isinstance(item, Post):
        return ModerationTarget.POST
    return ModerationTarget.MAP_ENTRY if isinstance(item, MapEntry) else ModerationTarget.COMMENT


type ItemStatus = PostStatus | CommentStatus | MapEntryStatus


def _published(item: Item) -> ItemStatus:
    if isinstance(item, Post):
        return PostStatus.PUBLISHED
    return MapEntryStatus.PUBLISHED if isinstance(item, MapEntry) else CommentStatus.PUBLISHED


def live_states(item: Item) -> set[str]:
    """Return the states in which an item is shown; an orphaned entry is shown too, at its widened place."""
    live = {PostStatus.PUBLISHED.value}
    return live | {MapEntryStatus.ORPHANED.value} if isinstance(item, MapEntry) else live


def _held(item: Item) -> ItemStatus:
    if isinstance(item, Post):
        return PostStatus.PENDING_REVIEW
    if isinstance(item, MapEntry):
        return MapEntryStatus.PENDING_REVIEW
    return CommentStatus.PENDING_REVIEW


def _removed(item: Item) -> ItemStatus:
    if isinstance(item, Post):
        return PostStatus.REMOVED
    return MapEntryStatus.REMOVED if isinstance(item, MapEntry) else CommentStatus.REMOVED


async def _restored(db: AsyncSession, item: Item) -> ItemStatus:
    """
    Return the state an approved item comes back to.

    A widened entry nobody sponsors goes back to `orphaned`, not `published`: approval must not
    turn an anonymous entry into one that is shown as the author's, and its widened level never
    changes. A sponsored one is published, as it was. Anything else is simply published.
    """
    if isinstance(item, MapEntry) and item.widened_level is not None:
        sponsored = await db.scalar(
            select(MapEntrySponsorship.id).where(MapEntrySponsorship.entry_id == item.id)
        )
        return MapEntryStatus.PUBLISHED if sponsored else MapEntryStatus.ORPHANED
    return _published(item)


def log_action(
    db: AsyncSession,
    item: Item,
    action: ModerationActionKind,
    source: ModerationSource,
    *,
    actor_id: uuid.UUID | None = None,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Add one row to the moderation log; the caller's transaction decides when it lands."""
    db.add(
        ModerationAction(
            target_type=_target(item),
            target_id=item.id,
            action=action,
            source=source,
            actor_id=actor_id,
            reason=reason,
            details=details or None,
        )
    )


def _set_state(item: Item, status: ItemStatus, reason: str | None, now: datetime) -> None:
    # The three kinds share the state names they use, so one assignment serves them all.
    item.status = status
    item.status_reason = reason
    item.reviewed_at = now


async def _close_reports(
    db: AsyncSession, item: Item, status: ReportStatus, actor_id: uuid.UUID | None
) -> None:
    """Close the open reports of an item with the decision that answers them."""
    await db.execute(
        update(Report)
        .where(
            Report.target_type == ReportTarget(_target(item).value),
            Report.target_id == item.id,
            Report.status == ReportStatus.OPEN,
        )
        .values(status=status, handled_at=clock.utcnow(), handled_by=actor_id)
    )


# ─── The guard's verdict ───────────────────────────────────────────────────────


def settle(db: AsyncSession, item: Item, verdict: GuardVerdict) -> None:
    """Apply the guard's verdict to a freshly submitted post or comment, and log it."""
    now = clock.utcnow()
    published = PostStatus.PUBLISHED if isinstance(item, Post) else CommentStatus.PUBLISHED
    held = PostStatus.PENDING_REVIEW if isinstance(item, Post) else CommentStatus.PENDING_REVIEW
    refused = PostStatus.REJECTED if isinstance(item, Post) else CommentStatus.REJECTED
    if verdict.outcome is Outcome.ALLOW:
        _set_state(item, published, None, now)
        if isinstance(item, Post):
            item.published_at = now
        action = ModerationActionKind.PUBLISHED
    elif verdict.outcome is Outcome.REVIEW:
        _set_state(item, held, verdict.reason, now)
        action = ModerationActionKind.HELD
    else:
        _set_state(item, refused, verdict.reason, now)
        action = ModerationActionKind.REJECTED
    log_action(
        db, item, action, ModerationSource.GUARD, reason=verdict.reason, details=verdict.details
    )


# ─── A moderator's decisions ───────────────────────────────────────────────────


def known_reason(reason: str | None) -> str | None:
    """Return the reason only if it is a code the app defines, never a moderator's own words."""
    known = messages_for().outcome_reasons.keys() | messages_for().reason_labels.keys()
    return reason if reason in known else None


def _wrong_state() -> AppError:
    return AppError(
        ErrorCode.CONFLICT,
        "This decision does not apply to the item as it is now.",
        status_code=409,
    )


async def _lock(db: AsyncSession, item: Item, allowed: set[str]) -> None:
    """
    Lock the item, read it fresh, and refuse a decision that does not fit its state.

    The author may have withdrawn the post, or another moderator may have decided, since the
    moderator's screen was drawn: a decision made on that screen must not undo it. A post its
    author withdrew is never brought back, and a draft was never submitted, so neither is in
    any set of states a decision applies to.
    """
    await db.refresh(item, with_for_update=True)
    owner_withdrew = (isinstance(item, Post) and item.removal_source is RemovalSource.OWNER) or (
        isinstance(item, MapEntry) and item.status is MapEntryStatus.WITHDRAWN
    )
    if owner_withdrew or item.status not in allowed:
        raise _wrong_state()


async def _drop_sponsorship(db: AsyncSession, entry: MapEntry) -> None:
    """Delete the sponsorship of an entry a moderator takes down: the sponsor's words go with it."""
    await db.execute(delete(MapEntrySponsorship).where(MapEntrySponsorship.entry_id == entry.id))


async def _sync_photo(db: AsyncSession, item: Item, photos: PhotoStore | None) -> None:
    """After a post or an entry changes state, make or delete the public copy of its photo."""
    if photos is None or isinstance(item, Comment):
        return
    if isinstance(item, MapEntry):
        insight_id: int | None = item.insight_id if item.with_photo else None
    else:
        insight_id = await db.scalar(
            select(InsightPublication.insight_id).where(
                InsightPublication.id == item.publication_id,
                InsightPublication.photo_ref.is_not(None),
            )
        )
    await photo_service.sync_public_copy(db, photos, insight_id)


async def approve(
    db: AsyncSession, item: Item, actor_id: uuid.UUID, *, photos: PhotoStore | None = None
) -> None:
    """
    Publish a held or refused item, or restore one a moderator removed.

    With `photos`, a post or an entry that shows a photo gets its public copy back.
    """
    await _lock(
        db,
        item,
        {PostStatus.PENDING_REVIEW.value, PostStatus.REJECTED.value, PostStatus.REMOVED.value},
    )
    was = item.status
    now = clock.utcnow()
    _set_state(item, await _restored(db, item), None, now)
    item.reviewed_by = actor_id
    if isinstance(item, Post | MapEntry):
        item.published_at = item.published_at or now
        item.removed_at = None
    if isinstance(item, Post):
        item.removal_source = None
    restored = was in {PostStatus.REMOVED.value, PostStatus.REJECTED.value}
    action = ModerationActionKind.RESTORED if restored else ModerationActionKind.PUBLISHED
    log_action(db, item, action, ModerationSource.MODERATOR, actor_id=actor_id)
    await _close_reports(db, item, ReportStatus.DISMISSED, actor_id)
    await _sync_photo(db, item, photos)


async def reject(
    db: AsyncSession,
    item: Item,
    actor_id: uuid.UUID,
    reason: str,
    *,
    photos: PhotoStore | None = None,
) -> None:
    """
    Refuse a held item; its author is told why.

    With `photos`, a public copy of the photo the item still had (an item held by reports was
    published before) is deleted: a refusal is a moderator's removal.
    """
    await _lock(db, item, {PostStatus.PENDING_REVIEW.value})
    now = clock.utcnow()
    # A map entry has no words to refuse: a held one that is not approved is removed.
    if isinstance(item, MapEntry):
        _set_state(item, MapEntryStatus.REMOVED, reason, now)
        item.removed_at = now
        await _drop_sponsorship(db, item)
    else:
        _set_state(
            item,
            PostStatus.REJECTED if isinstance(item, Post) else CommentStatus.REJECTED,
            reason,
            now,
        )
    item.reviewed_by = actor_id
    log_action(
        db,
        item,
        ModerationActionKind.REJECTED,
        ModerationSource.MODERATOR,
        actor_id=actor_id,
        reason=reason,
    )
    await _close_reports(db, item, ReportStatus.ACTIONED, actor_id)
    await _sync_photo(db, item, photos)


async def remove(
    db: AsyncSession,
    item: Item,
    actor_id: uuid.UUID,
    reason: str,
    *,
    photos: PhotoStore | None = None,
) -> None:
    """
    Take a published item down; everyone but the moderators stops seeing it at once.

    With `photos`, the public copy of the photo a post or an entry showed is deleted too.
    """
    await _lock(db, item, live_states(item))
    now = clock.utcnow()
    _set_state(item, _removed(item), reason, now)
    if isinstance(item, MapEntry):
        await _drop_sponsorship(db, item)
    item.reviewed_by = actor_id
    if isinstance(item, Post | MapEntry):
        item.removed_at = now
    if isinstance(item, Post):
        item.removal_source = RemovalSource.MODERATOR
    log_action(
        db,
        item,
        ModerationActionKind.REMOVED,
        ModerationSource.MODERATOR,
        actor_id=actor_id,
        reason=reason,
    )
    await _close_reports(db, item, ReportStatus.ACTIONED, actor_id)
    await _sync_photo(db, item, photos)


# ─── Reports moving a published item back to the queue ─────────────────────────


async def hold_if_reported(
    db: AsyncSession, item: Item, threshold: int, *, photos: PhotoStore | None = None
) -> bool:
    """
    Send a published item back to the queue once enough different people have reported it.

    It is hidden until a moderator decides, which a brigade of reports could abuse, so the
    number is a setting and 0 turns this off. With `photos`, the public copy of the photo it
    showed goes with it; a later approval makes the copy again. Returns whether the item was held.
    """
    if threshold <= 0 or item.status not in live_states(item):
        return False
    reporters = await db.scalar(
        select(func.count(func.distinct(Report.reporter_id))).where(
            Report.target_type == ReportTarget(_target(item).value),
            Report.target_id == item.id,
            Report.status == ReportStatus.OPEN,
        )
    )
    if (reporters or 0) < threshold:
        return False
    _set_state(item, _held(item), HELD_BY_REPORTS, clock.utcnow())
    log_action(
        db,
        item,
        ModerationActionKind.HELD,
        ModerationSource.REPORTS,
        reason=HELD_BY_REPORTS,
        details={"reporters": reporters},
    )
    await _sync_photo(db, item, photos)
    return True
