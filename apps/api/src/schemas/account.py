"""The export of everything an account owns."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.atlas import MapEntryOwnerOut
from src.schemas.cookie_consent import CookieConsentExport
from src.schemas.profile import ConsentOut, ProfileOut
from src.schemas.public_id import PublicId
from src.schemas.social_export import SocialExport


class UserExport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    # The public identity chosen for the social network, when there is one.
    handle: str | None
    public_name: str | None
    is_admin: bool
    is_active: bool
    email_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime


class OAuthAccountExport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    subject: str
    created_at: datetime


class SessionExport(BaseModel):
    """A session without its token hash, which is a credential."""

    model_config = ConfigDict(from_attributes=True)

    created_at: datetime
    expires_at: datetime
    last_seen_at: datetime
    ip_hash: str | None
    user_agent: str | None


# ─── The scan workflow: what a learner saved, by reference; never a photo ───


class ScanExport(BaseModel):
    """A scan without its photo, which is never kept beyond the hour it is needed."""

    model_config = ConfigDict(from_attributes=True)

    id: PublicId
    source: str
    status: str
    outcome: str | None
    engine: str
    sensitive: bool
    scene: dict[str, Any] | None
    focus: dict[str, Any] | None
    clarification_question: str | None
    clarification_answer: str | None
    created_at: datetime
    finished_at: datetime | None


class InsightExport(BaseModel):
    """An insight with its evidence by reference: the texts themselves are public, in the store."""

    model_config = ConfigDict(from_attributes=True)

    id: PublicId
    scan_id: PublicId | None
    origin: str
    tutorial_slug: str | None
    engine: str
    title: str
    glimpse: str
    relation: str
    quran_surah: int | None
    quran_ayah: int | None
    hadith_collection: str | None
    hadith_number: str | None
    explanation: list[dict[str, Any]]
    why: dict[str, Any]
    small_step: dict[str, Any] | None
    learning_unit_id: str | None
    action_state: str | None
    action_at: datetime | None
    completed_at: datetime | None
    place_id: PublicId | None
    published_at: datetime | None
    withdrawn_at: datetime | None
    created_at: datetime


class ChatMessageExport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    insight_id: PublicId
    question: str
    answer: str | None
    level: str | None
    # What was shown when the answer was written, and whether it is no longer shown.
    evidence_ids: list[str] | None
    withdrawn: bool
    created_at: datetime


class PlaceExport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PublicId
    region_id: str
    created_at: datetime
    last_visited_at: datetime | None


class RevealExport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PublicId
    insight_id: PublicId
    place_id: PublicId
    concept_key: str
    region_id: str
    layout_version: str
    slot: int
    theme: str
    x: float
    y: float
    radius: float
    learned_at: datetime
    created_at: datetime
    shown_at: datetime | None


class TreasureExport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    insight_id: PublicId
    kind: str
    quran_surah: int | None
    quran_ayah: int | None
    hadith_collection: str | None
    hadith_number: str | None
    learning_unit_id: str
    created_at: datetime
    revealed_at: datetime | None


class LearnerUnitExport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    path_version: str
    unit_id: str
    seen_count: int
    opened_count: int
    completed_count: int
    created_at: datetime
    last_at: datetime


class ExposureExport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    at: datetime
    kind: str
    insight_id: PublicId | None
    quran_surah: int | None
    quran_ayah: int | None
    hadith_collection: str | None
    hadith_number: str | None
    concept: str | None
    learning_unit_id: str | None


class PhotoExport(BaseModel):
    """
    A photo «تمّ» kept with the owner's consent (v2 §19): which insight, and whether a copy is public.

    The export says that the photo exists; the image itself is not in the file, and neither are
    the keys of its copies.
    """

    insight_id: PublicId
    published: bool = Field(description="A post or a map entry shows a public copy right now")


class LearningExport(BaseModel):
    """Everything the scan workflow keeps for the account."""

    scans: list[ScanExport]
    insights: list[InsightExport]
    chat_messages: list[ChatMessageExport]
    places: list[PlaceExport]
    reveals: list[RevealExport]
    treasures: list[TreasureExport]
    learner_units: list[LearnerUnitExport]
    exposures: list[ExposureExport]
    photos: list[PhotoExport]


class AccountExport(BaseModel):
    """
    Everything the account owns so far, for its owner.

    A table that gets a user id later must be added here and to the deletion in
    `account_service`; a test fails when a table references `users` without a cascade.
    """

    exported_at: datetime
    user: UserExport
    oauth_accounts: list[OAuthAccountExport]
    sessions: list[SessionExport]
    profile: ProfileOut
    consents: list[ConsentOut]
    # The cookie choices made while signed in, never the anonymous ones of the same browser.
    cookie_consents: list[CookieConsentExport]
    # What the account wrote and did on the social network.
    social: SocialExport
    # The insights placed on the atlas, with the exact points their owner gave.
    map_entries: list[MapEntryOwnerOut]
    learning: LearningExport
