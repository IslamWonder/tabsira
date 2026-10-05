"""
A published insight, for anyone: no sign-in, no cookie, nothing private.

Only an insight its owner has made public answers; any other id (unpublished, withdrawn, a
guest's, a closed account's, unknown) answers the same 404. The answer is never cached (the no-store
middleware covers errors too), so a withdrawal takes effect at once.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.deps import DbDep, PhotoStoreDep, requires
from src.errors import ErrorCode
from src.features import FeatureFlag
from src.scans.deps import PublicIdPath
from src.schemas.insight import PublicInsightOut
from src.services import public_insight_service

router = APIRouter(prefix="/public/insights", tags=["public"])


@router.get(
    "/{insight_id}",
    summary="One published insight, its scripture read from the store",
    dependencies=[Depends(requires(FeatureFlag.WORLD, code=ErrorCode.FEATURE_DISABLED))],
)
async def get_public_insight(
    insight_id: PublicIdPath, db: DbDep, photos: PhotoStoreDep
) -> PublicInsightOut:
    """Return the published insight: verse and hadith as stored, the author only if chosen."""
    return await public_insight_service.read_public(db, insight_id, photos)
