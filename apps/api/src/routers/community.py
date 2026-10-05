"""The community summary for the home page: aggregate public counts, no account needed."""

from __future__ import annotations

import logging
from http import HTTPStatus

from fastapi import APIRouter
from sqlalchemy.exc import SQLAlchemyError

from src.deps import DbDep, SettingsDep
from src.errors import AppError, ErrorCode, ErrorResponse
from src.schemas.community import CommunitySummary
from src.services import community_service

log = logging.getLogger("tabsira.community")

router = APIRouter(tags=["community"])


@router.get(
    "/community/summary",
    summary="Aggregate counts of the public community",
    responses={HTTPStatus.SERVICE_UNAVAILABLE: {"model": ErrorResponse}},
)
async def community_summary(settings: SettingsDep, db: DbDep) -> CommunitySummary:
    """
    Count members, published insights, atlas entries, countries and reactions; never a person.

    The answer is kept ten minutes per worker. A database that is down or slow answers 503 at
    once, so the home page that asks can leave the box out and still load.
    """
    try:
        return await community_service.summary(db, settings.features)
    except (SQLAlchemyError, OSError, TimeoutError) as error:
        log.warning("community summary unavailable (%s)", type(error).__name__)
        raise AppError(
            ErrorCode.SERVICE_UNAVAILABLE,
            "The community summary is unavailable.",
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        ) from error
