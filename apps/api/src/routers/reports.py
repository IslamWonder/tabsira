"""Reports of posts, comments and map entries, with a reason."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from src.deps import (
    DbDep,
    PhotoStoreDep,
    SettingsDep,
    VerifiedUser,
    limited,
    require_social_or_atlas,
)
from src.schemas.social import ReportIn, ReportOut
from src.services import report_service
from src.services.social_limits import WriteKind

router = APIRouter(tags=["reports"], dependencies=[Depends(require_social_or_atlas)])


@router.post(
    "/reports",
    status_code=status.HTTP_201_CREATED,
    summary="Report a post, a comment or a map entry",
    dependencies=[limited(WriteKind.REPORT)],
)
async def report(
    body: ReportIn, user: VerifiedUser, db: DbDep, settings: SettingsDep, photos: PhotoStoreDep
) -> ReportOut:
    """
    Tell the moderators about something the caller may read.

    The reasons include a false attribution of a religious claim, a photo published without
    permission, a place that is not right and a location or photo that gives away private
    information. 404 for what the caller may not read, and for a target whose feature is switched
    off, 400 for their own words. Reporting the same thing twice answers with the first report. Enough different reporters send a published
    item back to the moderation queue (`SOCIAL_REPORT_HOLD_THRESHOLD`), and the public copy of a
    photo it showed is deleted until a moderator approves it.
    """
    report_id = await report_service.file_report(
        db,
        user,
        target_type=body.target_type,
        target_id=body.target_id,
        reason=body.reason,
        details=body.details,
        hold_threshold=settings.social_report_hold_threshold,
        social_on=settings.feature_social,
        atlas_on=settings.feature_atlas,
        photos=photos,
    )
    await db.commit()
    return ReportOut(id=report_id)
