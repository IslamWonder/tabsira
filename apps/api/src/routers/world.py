"""The learner's world (v2 §16) and its hidden treasures (v2 §17)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from src.deps import DbDep, SettingsDep, requires
from src.errors import ErrorCode
from src.features import FeatureFlag
from src.owner import OptionalOwner
from src.scans.deps import PublicIdPath
from src.schemas.world import RevealsShownIn, TreasureOut, WorldOut, WorldPlaceOut
from src.services import world_service

router = APIRouter(
    prefix="/world",
    tags=["world"],
    dependencies=[Depends(requires(FeatureFlag.WORLD, code=ErrorCode.FEATURE_DISABLED))],
)


@router.get("", summary="The map: regions under fog, the places that came out of it, threads")
async def get_world(db: DbDep, settings: SettingsDep, owner: OptionalOwner) -> WorldOut:
    """
    Return every region with its fog, the caller's places, threads and ready treasures.

    A newcomer gets the whole map under fog: there is nothing to hide and nothing to make.
    A concept learned without a reveal yet (before reveals existed, or with the world
    off) gets one here first, shown without its effect.
    """
    return await world_service.world(db, settings, owner)


@router.post(
    "/reveals/shown",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Record that the world played these reveals",
)
async def reveals_shown(body: RevealsShownIn, db: DbDep, owner: OptionalOwner) -> Response:
    """
    Mark the caller's reveals as shown, so their effect never plays again; asking again changes nothing.

    Ids of another owner's reveals, or of none, are ignored, never reported.
    """
    await world_service.mark_shown(db, owner, body.ids)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/places/{place_id}/visit", summary="Open a place: a return can show its treasure")
async def visit_place(
    place_id: PublicIdPath, db: DbDep, settings: SettingsDep, owner: OptionalOwner
) -> WorldPlaceOut:
    """Record the visit and return the place with its insights and a treasure that is ready."""
    return await world_service.visit(db, settings, owner, place_id)


@router.post(
    "/treasures/{treasure_id}/reveal",
    summary="Reveal a treasure that is ready",
    dependencies=[Depends(requires(FeatureFlag.TREASURE, code=ErrorCode.FEATURE_DISABLED))],
)
async def reveal_treasure(
    treasure_id: PublicIdPath, db: DbDep, settings: SettingsDep, owner: OptionalOwner
) -> TreasureOut:
    """Return the treasure's verified text from the store; 409 TREASURE_NOT_READY before the return."""
    return await world_service.reveal(db, settings, owner, treasure_id)
