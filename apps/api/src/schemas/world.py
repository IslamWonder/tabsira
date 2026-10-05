"""What the world routes return: a fixed map, the places and reveals the fog left, threads, treasures."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from src.models import RelationReason, TreasureKind, WorldTheme
from src.schemas.insight import InsightHadith, InsightQuran
from src.schemas.public_id import PublicId


class PositionOut(BaseModel):
    x: float
    y: float


class RegionOut(BaseModel):
    id: str
    domain_id: str
    name: str
    domain_title: str
    position: PositionOut
    fog: bool = Field(description="True until an insight of this region is completed")
    place_id: PublicId | None


class PlaceInsightOut(BaseModel):
    id: PublicId
    title: str
    completed_at: datetime
    reveal_id: PublicId | None = Field(
        description="The reveal of the insight's concept, made by it or by an earlier insight "
        "of the same concept; null when its region had no room left"
    )


class TreasureFlag(BaseModel):
    """A treasure ready to be revealed; its content stays hidden until the reveal."""

    id: PublicId


class WorldPlaceOut(BaseModel):
    id: PublicId
    region_id: str
    name: str
    created_at: datetime
    last_visited_at: datetime | None
    insights: list[PlaceInsightOut]
    treasure: TreasureFlag | None


class RelationOut(BaseModel):
    place_a_id: PublicId
    place_b_id: PublicId
    reason: RelationReason
    reason_label: str
    question: str
    insight_ids: list[PublicId]


class RevealOut(BaseModel):
    """A circle of the world picture one learned concept lifted from the clouds (decision 59)."""

    id: PublicId
    place_id: PublicId
    region_id: str
    insight_id: PublicId = Field(description="The first completed insight of the concept")
    landmark: bool = Field(
        description="The region's landmark (its first reveal), where its marker stands"
    )
    theme: WorldTheme
    icon: str = Field(description="The landmark's drawing in the web app's icon set")
    x: float = Field(description="The centre, as a ratio of the picture's width from the left")
    y: float = Field(description="The centre, as a ratio of the picture's height from the top")
    radius: float = Field(description="As a ratio of the picture's width")
    learned_at: datetime
    shown: bool = Field(
        description="The world already played this reveal; until then it plays once"
    )


class WorldOut(BaseModel):
    version: str
    path_version: str
    layout_version: str = Field(description="The version of the world picture's layout")
    regions: list[RegionOut]
    places: list[WorldPlaceOut]
    relations: list[RelationOut]
    reveals: list[RevealOut] = Field(description="The owner's reveals, in the order learned")


class RevealsShownIn(BaseModel):
    """The reveals whose effect the world just played, so it never plays them again."""

    ids: Annotated[list[PublicId], Field(min_length=1, max_length=200)]


class TreasureUnitOut(BaseModel):
    id: str
    title: str


class TreasureOut(BaseModel):
    id: PublicId
    kind: TreasureKind
    kind_label: str
    insight_id: PublicId
    place_id: PublicId
    quran: InsightQuran | None
    hadith: InsightHadith | None
    learning_unit: TreasureUnitOut | None
    revealed_at: datetime | None
    disclosure: str
