"""What the insight routes return: scripture by reference from the store, the platform's words apart."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from src.models import ActionState, InsightOrigin
from src.pipeline.engine import RelationType
from src.pipeline.schemas import BBox
from src.routers.scripture import HadithOut, QuranVerseOut
from src.schemas.public_id import PublicId

MAX_QUESTION_CHARS = 500


class EvidenceWhy(BaseModel):
    """Why the engine chose a text: the kind of link and what it matched on."""

    relation: RelationType
    relation_label: str
    matched_on: str


class InsightQuran(BaseModel):
    tag: str = Field(description="«القرآن»: the fixed tag of quoted Quran")
    verse: QuranVerseOut = Field(description="The verse exactly as stored, with its hash and link")
    why: EvidenceWhy | None


class InsightHadith(BaseModel):
    tag: str = Field(description="«السنة»: the fixed tag of quoted Sunnah")
    hadith: HadithOut = Field(
        description="The hadith exactly as stored, its spans, its dorar.net ruling and links"
    )
    why: EvidenceWhy | None


class ExplanationOut(BaseModel):
    section: Literal["seen", "value", "quran", "sunnah", "life"]
    label: str
    text: str


class InsightWhyOut(BaseModel):
    """«لماذا ظهر هذا؟»: the clues, the concept, the limits, the reason of a personal choice."""

    visible_clues: list[str]
    concept: str
    limits: list[str]
    personalised_because: str | None


class StepOut(BaseModel):
    text: str
    kind: Literal["text_grounded", "ethical_application", "reflection"]
    label: str = Field(description="«من السنة» when grounded in a shown text, else «اقتراح عملي»")


class ActionOut(BaseModel):
    """What the learner declared about the small step: a statement, never a proof or a reward."""

    state: ActionState | None
    at: datetime | None
    means: str | None


class ChatMessageOut(BaseModel):
    question: str
    answer: str
    level: Literal["a", "b", "c", "d"]
    kind: Literal["answer", "referral", "new_search"]
    answered_at: datetime


class ChatOut(BaseModel):
    enabled: bool
    used: int
    limit: int
    remaining: int
    messages: list[ChatMessageOut]


class LearningUnitOut(BaseModel):
    id: str
    title: str
    domain_id: str
    path_version: str


class InsightImageOut(BaseModel):
    """Whether the photo of the insight's scan may be shown; never for a sensitive scene."""

    sensitive: bool
    url: str | None


class InsightDetailOut(BaseModel):
    id: PublicId
    scan_id: PublicId | None
    origin: InsightOrigin
    engine: str = Field(description="`pipeline`, `demo` (a declared simulation) or `prepared`")
    label: str | None = Field(
        description="«مثال موثّق مُعدّ» or the simulation notice, when one applies"
    )
    title: str
    glimpse: str
    anchor: BBox | None
    relation: RelationType
    relation_label: str
    quran: InsightQuran | None
    hadith: InsightHadith | None
    hadith_status: Literal["shown", "awaiting_verification", "none"]
    notice: str | None = Field(description="Set when the hadith waits for its dorar.net ruling")
    pair_complete: bool
    explanation_tag: str
    explanation: list[ExplanationOut]
    why: InsightWhyOut
    small_step: StepOut | None
    learning_unit: LearningUnitOut | None
    action: ActionOut
    chat: ChatOut
    image: InsightImageOut
    completed_at: datetime | None
    place_id: PublicId | None
    created_at: datetime
    disclosure: str


class ActionIn(BaseModel):
    """«نفّذته» (`done`) or «سأفعله لاحقًا» (`later`)."""

    choice: ActionState


class ChatIn(BaseModel):
    message: Annotated[str, Field(min_length=1, max_length=MAX_QUESTION_CHARS)]
    # The same key for a retry, a refresh or a double send: answered and counted once.
    idempotency_key: Annotated[
        str, Field(alias="idempotencyKey", min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    ]


class ChatReply(BaseModel):
    message: ChatMessageOut
    used: int
    limit: int
    remaining: int
    disclosure: str


class AfterOption(BaseModel):
    id: Literal["open_world", "new_scan", "share"]
    label: str


class PlaceOut(BaseModel):
    id: PublicId
    region_id: str
    name: str
    created: bool = Field(description="The fog lifted from this place with this completion")


class CompletionOut(BaseModel):
    insight_id: PublicId
    completed_at: datetime
    first_time: bool = Field(
        description="False when «تمّ» was already recorded: nothing was saved twice"
    )
    place: PlaceOut | None
    treasure_prepared: bool = Field(description="A hidden treasure waits; it shows on return")
    badges_earned: list[str]
    options: list[AfterOption]
    suggest_account: str | None = Field(description="Set for a guest after the first completion")
    disclosure: str
