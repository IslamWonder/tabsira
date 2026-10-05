"""What the insight routes return: scripture by reference from the store, the platform's words apart."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from src.models import ActionState, FeedbackReason, InsightOrigin
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
    link: str | None = Field(
        default=None,
        description="«وجه الصلة»: how the text's own meaning meets the scene, as the checker found it",
    )


class InsightQuran(BaseModel):
    tag: str = Field(description="«القرآن»: the fixed tag of quoted Quran")
    verse: QuranVerseOut = Field(description="The verse exactly as stored, with its hash and link")
    why: EvidenceWhy | None


class InsightHadith(BaseModel):
    tag: str = Field(description="«السنة»: the fixed tag of quoted Sunnah")
    hadith: HadithOut = Field(
        description="The hadith exactly as stored, with its spans; no ruling is shown (decision 65)"
    )
    why: EvidenceWhy | None


class PublicQuran(BaseModel):
    """A verse for a stranger: the text as stored, never the reason the engine chose it."""

    tag: str = Field(description="«القرآن»: the fixed tag of quoted Quran")
    verse: QuranVerseOut = Field(description="The verse exactly as stored, with its hash and link")


class PublicHadith(BaseModel):
    """A hadith for a stranger: the text as stored, never the reason the engine chose it."""

    tag: str = Field(description="«السنة»: the fixed tag of quoted Sunnah")
    hadith: HadithOut = Field(
        description="The hadith exactly as stored, with its spans; no ruling is shown (decision 65)"
    )


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
    # A request for another text that found one: the text the answer names, read from the
    # store by its id (v2 §14); null on every other answer.
    quran: PublicQuran | None = Field(
        default=None, description="The verse the answer found after a new search, as stored"
    )
    hadith: PublicHadith | None = Field(
        default=None, description="The hadith the answer found after a new search, as stored"
    )


class ChatOut(BaseModel):
    enabled: bool
    closed: bool = Field(
        default=False, description="«تمّ» closed the insight: its messages stay, no new question"
    )
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
    has_photo: bool = Field(
        description="The owner's own copy was kept at «تمّ» (v2 §19), so a publication may "
        "offer to show it; the key itself is never served"
    )


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
    sound_url: str | None = Field(
        description="Path on this API of the sound effect of the insight's main ontology entity"
    )
    quran: InsightQuran | None
    hadith: InsightHadith | None
    hadith_status: Literal["shown", "none"]
    pair_complete: bool
    explanation_tag: str
    explanation: list[ExplanationOut]
    why: InsightWhyOut
    small_step: StepOut | None
    learning_unit: LearningUnitOut | None
    action: ActionOut
    chat: ChatOut
    image: InsightImageOut
    feedback: FeedbackOut | None = Field(
        default=None, description="The owner's own rating, never shown to anyone else"
    )
    completed_at: datetime | None
    place_id: PublicId | None
    published_at: datetime | None = Field(description="Set while the owner has the insight public")
    created_at: datetime
    disclosure: str


FEEDBACK_NOTE_MAX = 300


class FeedbackIn(BaseModel):
    """The owner's rating of the insight: useful or not, and why not."""

    helpful: bool
    reasons: list[FeedbackReason] = Field(
        default_factory=list,
        max_length=len(FeedbackReason),
        description="Why it was not useful; empty when it was",
    )
    note: str | None = Field(default=None, max_length=FEEDBACK_NOTE_MAX)

    @model_validator(mode="after")
    def _reasons_only_when_not_helpful(self) -> FeedbackIn:
        if self.helpful and self.reasons:
            message = "a useful insight carries no reason"
            raise ValueError(message)
        if len(set(self.reasons)) != len(self.reasons):
            message = "each reason once"
            raise ValueError(message)
        note = (self.note or "").strip()
        self.note = note or None
        return self


class FeedbackOut(BaseModel):
    helpful: bool
    reasons: list[FeedbackReason]
    note: str | None
    updated_at: datetime


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


class CompletionRevealOut(BaseModel):
    """What the completion lifted from the clouds of the world picture (decision 59)."""

    id: PublicId
    landmark: bool = Field(description="The region's landmark: the first concept learned there")
    created: bool = Field(
        description="Made by this completion; false when the concept was learned before"
    )


class CompletionOut(BaseModel):
    insight_id: PublicId
    completed_at: datetime
    first_time: bool = Field(
        description="False when «تمّ» was already recorded: nothing was saved twice"
    )
    place: PlaceOut | None
    reveal: CompletionRevealOut | None = Field(
        description="The reveal of the insight's concept; null with the world off, or when "
        "its region had no room left"
    )
    treasure_prepared: bool = Field(description="A hidden treasure waits; it shows on return")
    badges_earned: list[str]
    options: list[AfterOption]
    suggest_account: str | None = Field(description="Set for a guest after the first completion")
    disclosure: str


class PublicationOut(BaseModel):
    """Whether the owner's insight is public, and since when."""

    insight_id: PublicId
    published: bool
    published_at: datetime | None
    path: str | None = Field(description="The public page's path on the web app, when public")


class PublicAuthorOut(BaseModel):
    """The only things a public insight says about its owner: the handle, and the name if consented."""

    handle: str
    public_name: str | None


class PublicInsightOut(BaseModel):
    """
    A published insight for any reader: scripture from the store, nothing of the owner's.

    There is no scan, no location, no chat, no progress, no «لماذا ظهر هذا؟» (its
    clues describe the photo and its reason may be personal), no `why` beside a text and no
    «ما ظهر» part (it describes the photo); the author is
    present only when the owner chose a public handle and name. The photo is there only when
    its owner already published it (a public post or map entry made its public copy).
    """

    id: PublicId
    engine: str = Field(description="`pipeline`, `demo` (a declared simulation) or `prepared`")
    label: str | None
    title: str
    glimpse: str
    relation: RelationType
    relation_label: str
    quran: PublicQuran | None
    hadith: PublicHadith | None
    hadith_status: Literal["shown", "none"]
    pair_complete: bool
    explanation_tag: str
    explanation: list[ExplanationOut]
    small_step: StepOut | None
    author: PublicAuthorOut | None
    published_at: datetime
    photo_url: str | None = Field(
        default=None,
        description="The photo's public copy, only when its owner already published the photo",
    )
    disclosure: str
