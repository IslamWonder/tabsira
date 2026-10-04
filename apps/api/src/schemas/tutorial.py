"""What `GET /tutorial/rain` returns: a prepared example, labelled as such, hydrated from the store."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.pipeline.engine import RelationType
from src.pipeline.schemas import BBox
from src.schemas.insight import ExplanationOut, InsightHadith, InsightQuran, InsightWhyOut, StepOut


class TutorialImageOut(BaseModel):
    path: str = Field(description="Path of the photo in the web app")
    width: int
    height: int
    alt: str


class TutorialInsightOut(BaseModel):
    slug: str
    title: str
    glimpse: str
    anchor: BBox
    relation: RelationType
    relation_label: str
    quran: InsightQuran
    hadith: InsightHadith | None
    hadith_status: Literal["shown", "awaiting_verification", "none"]
    notice: str | None = Field(description="Set while the hadith waits for its dorar.net ruling")
    pair_complete: bool
    explanation_tag: str
    explanation: list[ExplanationOut]
    why: InsightWhyOut
    small_step: StepOut | None
    learning_unit_id: str


class TutorialOut(BaseModel):
    scene: str
    version: str
    title: str
    label: str = Field(description="«مثال موثّق مُعدّ»")
    status: Literal["prepared"] = Field(
        description="Prepared, reviewed content; never live analysis"
    )
    image: TutorialImageOut
    insights: list[TutorialInsightOut]
    disclosure: str
