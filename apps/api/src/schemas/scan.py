"""What the scan routes take and return."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, Field, model_validator

from src.models import ScanOutcome, ScanSource, ScanStatus
from src.pipeline.engine import RelationType
from src.pipeline.schemas import BBox, EntityOrigin, EvidenceStatus
from src.schemas.public_id import PublicId

MAX_URL_LENGTH = 2048
MAX_ANSWER_CHARS = 300
MAX_LABEL_CHARS = 60


class ScanFromUrl(BaseModel):
    """A photo given by its public address; the server fetches it (v2 §6)."""

    url: Annotated[str, Field(min_length=8, max_length=MAX_URL_LENGTH)]


class FocusIn(BaseModel):
    """What the learner pointed at: one thing the scene found, or a box drawn on the photo."""

    entity_id: Annotated[str, Field(min_length=1, max_length=32)] | None = None
    box: BBox | None = None
    # What the learner says the box holds; optional, their own words.
    label: Annotated[str, Field(min_length=1, max_length=MAX_LABEL_CHARS)] | None = None

    @model_validator(mode="after")
    def _one_target(self) -> Self:
        if (self.entity_id is None) == (self.box is None):
            message = "give either entity_id or box"
            raise ValueError(message)
        if self.box is not None and (
            self.box.x + self.box.width > 1 or self.box.y + self.box.height > 1
        ):
            message = "the box must lie inside the photo"
            raise ValueError(message)
        if self.box is not None and (self.box.width == 0 or self.box.height == 0):
            message = "the box must have an area"
            raise ValueError(message)
        return self


class ClarifyIn(BaseModel):
    """The learner's answer to the one question the scan asked."""

    answer: Annotated[str, Field(min_length=1, max_length=MAX_ANSWER_CHARS)]


class ScanEntityOut(BaseModel):
    id: str
    label_arabic: str
    bbox: BBox | None
    origin: EntityOrigin
    status: EvidenceStatus


class ScanImageOut(BaseModel):
    """Whether the photo can still be shown to its owner; never for a sensitive scene."""

    available: bool
    width: int | None
    height: int | None
    url: str | None = Field(description="Path of the photo on this API while it is kept")


class InsightSummary(BaseModel):
    id: PublicId
    title: str
    glimpse: str
    anchor: BBox | None
    relation: RelationType
    relation_label: str
    completed: bool


class ScanOut(BaseModel):
    id: PublicId
    status: ScanStatus
    outcome: ScanOutcome | None
    error_code: str | None = Field(description="A stable code (v2 §26) when the scan failed")
    run: int
    engine: str
    engine_label: str | None = Field(description="Set when the engine is a declared simulation")
    source: ScanSource
    sensitive: bool
    image: ScanImageOut
    description: str | None
    entities: list[ScanEntityOut]
    clarification_question: str | None
    insights: list[InsightSummary]
    events_url: str
    created_at: datetime
    finished_at: datetime | None
    disclosure: str
