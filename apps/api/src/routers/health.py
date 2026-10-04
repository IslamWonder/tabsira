"""Liveness and readiness endpoints."""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.deps import SettingsDep

log = logging.getLogger("tabsira.health")

router = APIRouter(tags=["health"])


class Liveness(BaseModel):
    status: Literal["ok"]


class Readiness(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, Literal["ok", "down"]]


@router.get("/health", summary="Liveness")
async def health() -> Liveness:
    """
    Report that the process is up and serving.

    Touches no dependency, so it stays cheap enough for a per-second probe and
    answers even when the database is down.
    """
    return Liveness(status="ok")


@router.get(
    "/health/ready",
    summary="Readiness",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": Readiness}},
)
async def readiness(
    response: Response,
    settings: SettingsDep,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Readiness:
    """
    Report whether this process can serve a request, which needs the database.

    The check is bounded by the connect timeout, so a database that is down or
    hangs answers 503 `degraded` quickly instead of holding the request.
    """
    try:
        async with asyncio.timeout(settings.db_connect_timeout):
            await session.execute(text("SELECT 1"))
    except Exception as error:
        log.warning("readiness: database check failed (%s)", type(error).__name__)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Readiness(status="degraded", checks={"database": "down"})
    return Readiness(status="ok", checks={"database": "ok"})
