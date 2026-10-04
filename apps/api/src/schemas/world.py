"""What the world routes return: a fixed map, the places the fog left, recorded threads, treasures."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from src.models import RelationReason, TreasureKind
from src.schemas.insight import InsightHadith, InsightQuran


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
    place_id: uuid.UUID | None


class PlaceInsightOut(BaseModel):
    id: uuid.UUID
    title: str
    completed_at: datetime


class TreasureFlag(BaseModel):
    """A treasure ready to be revealed; its content stays hidden until the reveal."""

    id: uuid.UUID


class PlaceOut(BaseModel):
    id: uuid.UUID
    region_id: str
    name: str
    created_at: datetime
    last_visited_at: datetime | None
    insights: list[PlaceInsightOut]
    treasure: TreasureFlag | None


class RelationOut(BaseModel):
    place_a_id: uuid.UUID
    place_b_id: uuid.UUID
    reason: RelationReason
    reason_label: str
    question: str
    insight_ids: list[uuid.UUID]


class WorldOut(BaseModel):
    version: str
    path_version: str
    regions: list[RegionOut]
    places: list[PlaceOut]
    relations: list[RelationOut]


class TreasureUnitOut(BaseModel):
    id: str
    title: str


class TreasureOut(BaseModel):
    id: uuid.UUID
    kind: TreasureKind
    kind_label: str
    insight_id: uuid.UUID
    place_id: uuid.UUID
    quran: InsightQuran | None
    hadith: InsightHadith | None
    learning_unit: TreasureUnitOut | None
    revealed_at: datetime | None
    disclosure: str
