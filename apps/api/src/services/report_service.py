"""
Reports: a reader tells the moderators about a post, a comment or a map entry, with a reason.

Only what the reporter may read can be reported, a person cannot report their own words, and
one reporter reports one thing once (a second report is answered with the first). A report
changes nothing by itself, with one exception that is a setting: enough different reporters
send a published item back to the moderation queue, hidden until a person decides.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors import AppError, ErrorCode
from src.models.atlas import MapEntry
from src.models.social import Comment, Post, Report, ReportReason, ReportTarget
from src.models.user import User
from src.services import atlas_service, comment_service, moderation_service, post_service
from src.storage.photos import PhotoStore


def _own() -> AppError:
    return AppError(ErrorCode.BAD_REQUEST, "You cannot report your own words.", status_code=400)


def _switched_off() -> AppError:
    return AppError(ErrorCode.NOT_FOUND, "Not found.", status_code=404)


async def _target(
    db: AsyncSession,
    reporter: User,
    target_type: ReportTarget,
    target_id: int,
    *,
    social_on: bool,
    atlas_on: bool,
) -> Post | Comment | MapEntry:
    """
    Load what is reported, or raise 404 when the reporter may not read it.

    A target whose feature is switched off is 404 too: the atlas alone opens map entries to
    reports, the network alone posts and comments, and neither says what the other holds.
    """
    if target_type is ReportTarget.MAP_ENTRY:
        if not atlas_on:
            raise _switched_off()
        entry = await atlas_service.published_entry(db, target_id, reporter)
        if entry.user_id == reporter.id:
            raise _own()
        return entry
    if not social_on:
        raise _switched_off()
    if target_type is ReportTarget.POST:
        row = await post_service.get_interactable(db, target_id, reporter)
        if row.post.author_id == reporter.id:
            raise _own()
        return row.post
    comment = await db.scalar(
        select(Comment).where(Comment.id == target_id, comment_service.visible_comment(reporter))
    )
    if comment is None:
        raise comment_service.not_found()
    await post_service.get_interactable(db, comment.post_id, reporter)
    if comment.author_id == reporter.id:
        raise _own()
    return comment


async def file_report(
    db: AsyncSession,
    reporter: User,
    *,
    target_type: ReportTarget,
    target_id: int,
    reason: ReportReason,
    details: str | None,
    hold_threshold: int,
    social_on: bool,
    atlas_on: bool,
    photos: PhotoStore | None = None,
) -> int:
    """
    File a report and return its id; the same report filed again returns the first one's.

    With `photos`, an item the reports hold loses the public copy of its photo at once.
    """
    target = await _target(
        db, reporter, target_type, target_id, social_on=social_on, atlas_on=atlas_on
    )
    created: int | None = await db.scalar(
        insert(Report)
        .values(
            reporter_id=reporter.id,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            details=details,
        )
        .on_conflict_do_nothing(
            index_elements=[Report.reporter_id, Report.target_type, Report.target_id]
        )
        .returning(Report.id)
    )
    if created is not None:
        await moderation_service.hold_if_reported(db, target, hold_threshold, photos=photos)
        return created
    first: int = (
        await db.execute(
            select(Report.id).where(
                Report.reporter_id == reporter.id,
                Report.target_type == target_type,
                Report.target_id == target_id,
            )
        )
    ).scalar_one()
    return first
