"""What `GET /me/progress` returns: practice only, never faith, never a comparison."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class NextRankOut(BaseModel):
    id: str
    title: str
    minimum: int


class RankOut(BaseModel):
    id: str
    title: str
    hint: str
    looks: int
    next: NextRankOut | None
    progress: float = Field(description="The way from this rank to the next, 0 to 1")


class DayOut(BaseModel):
    day: date
    looked: bool


class StreakOut(BaseModel):
    current: int
    best: int
    last_day: date | None
    days: list[DayOut] = Field(description="The last seven days, today first")


class QuestStepOut(BaseModel):
    id: str
    label: str
    done: bool


class QuestOut(BaseModel):
    title: str
    day: date
    steps: list[QuestStepOut]
    done: bool
    days_done: int


class StarOut(BaseModel):
    concept: str
    count: int
    first_seen: datetime
    x: float
    y: float


class SkyOut(BaseModel):
    count: int
    stars: list[StarOut]


class BadgeOut(BaseModel):
    id: str
    title: str
    description: str
    earned: bool
    earned_at: datetime | None


class CountsOut(BaseModel):
    looks: int
    completed: int
    actions_done: int
    places: int
    treasures: int
    questions: int


class ProgressOut(BaseModel):
    timezone: str
    rank: RankOut
    streak: StreakOut
    daily_quest: QuestOut
    sky: SkyOut
    badges: list[BadgeOut]
    counts: CountsOut
    disclaimer: str
