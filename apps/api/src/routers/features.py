"""The feature switches in force, so a client never guesses them (decision 63)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from src.deps import SettingsDep
from src.features import FeatureFlag

router = APIRouter(tags=["features"])


class FeaturesOut(BaseModel):
    features: list[FeatureFlag]


@router.get("/features", summary="The features that are switched on")
async def list_features(settings: SettingsDep) -> FeaturesOut:
    """Name the features that are on, parents applied; a feature not listed answers 404."""
    return FeaturesOut(features=sorted(settings.features))
