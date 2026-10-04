"""The learner's world (v2 §16) and its hidden treasures (v2 §17)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from src.deps import DbDep, SettingsDep
from src.owner import OptionalOwner
from src.scans.deps import feature
from src.schemas.world import PlaceOut, TreasureOut, WorldOut
from src.services import world_service

router = APIRouter(prefix="/world", tags=["world"], dependencies=[Depends(feature("world"))])


@router.get("", summary="The map: regions under fog, the places that came out of it, threads")
async def get_world(db: DbDep, settings: SettingsDep, owner: OptionalOwner) -> WorldOut:
    """
    Return every region with its fog, the caller's places, threads and ready treasures.

    A newcomer gets the whole map under fog: there is nothing to hide and nothing to make.
    """
    return await world_service.world(db, settings, owner)


@router.post("/places/{place_id}/visit", summary="Open a place: a return can show its treasure")
async def visit_place(
    place_id: uuid.UUID, db: DbDep, settings: SettingsDep, owner: OptionalOwner
) -> PlaceOut:
    """Record the visit and return the place with its insights and a treasure that is ready."""
    return await world_service.visit(db, settings, owner, place_id)


@router.post(
    "/treasures/{treasure_id}/reveal",
    summary="Reveal a treasure that is ready",
    dependencies=[Depends(feature("treasure"))],
)
async def reveal_treasure(
    treasure_id: uuid.UUID, db: DbDep, settings: SettingsDep, owner: OptionalOwner
) -> TreasureOut:
    """Return the treasure's verified text from the store; 409 TREASURE_NOT_READY before the return."""
    return await world_service.reveal(db, settings, owner, treasure_id)
