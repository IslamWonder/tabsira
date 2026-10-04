"""The learner's practice: ranks, streak, the daily quest, the sky of meanings, badges (decision 27)."""

from __future__ import annotations

from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Query

from src.deps import DbDep
from src.errors import AppError, ErrorCode
from src.owner import OptionalOwner
from src.schemas.progress import ProgressOut
from src.services import progress_service

router = APIRouter(prefix="/me", tags=["me"])


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise AppError(
            ErrorCode.VALIDATION_ERROR, "tz must be an IANA time zone.", status_code=422
        ) from None


@router.get("/progress", summary="Practice, never piety: ranks, streak, quest, sky, badges")
async def progress(
    db: DbDep,
    owner: OptionalOwner,
    tz: Annotated[
        str,
        Query(
            max_length=64,
            description="The learner's IANA time zone, for what «today» means; UTC by default",
        ),
    ] = "UTC",
) -> ProgressOut:
    """
    Return what the learner's recorded practice adds up to, with the practice disclaimer.

    Counted from looks, completions, declared steps, places, treasures and
    questions only; never faith, never reward, never a comparison with anyone.
    """
    zone = _zone(tz)
    return progress_service.describe(await progress_service.practice_log(db, owner), zone)
