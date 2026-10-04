"""What the world routes return: a fixed map, the places the fog left, recorded threads, treasures."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.models import RelationReason, TreasureKind
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


class WorldOut(BaseModel):
    version: str
    path_version: str
    regions: list[RegionOut]
    places: list[WorldPlaceOut]
    relations: list[RelationOut]


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
