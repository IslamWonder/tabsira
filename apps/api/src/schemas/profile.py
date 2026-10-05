"""
Request and response bodies of the profile and consent routes.

The religious background, the gender and the age range are private. They
appear in exactly two responses: `ProfileOut`, to its owner on `/profile`, and
`AccountExport`, which embeds it. A test lists every schema that carries one of
those fields, so a new response that leaks one fails the build.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from src.models.consent import ConsentKind
from src.models.profile import (
    AgeRange,
    Gender,
    Goal,
    KnowledgeLevel,
    ReducedMotion,
    ReligiousBackground,
    Theme,
)

_LANGUAGE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8}){0,3}$")
LANGUAGE_MAX = 35
# The five questions a completed profile has answered, `unknown` and `[]` included.
COMPLETION_FIELDS = frozenset(
    {"goals", "knowledge_level", "age_range", "religious_background", "gender"}
)
Version = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._-]{1,32}$")]


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    goals: list[Goal]
    knowledge_level: KnowledgeLevel
    age_range: AgeRange
    religious_background: ReligiousBackground
    gender: Gender
    language: str
    personalization_enabled: bool
    memory_enabled: bool
    photo_storage_consent: bool
    theme: Theme
    reduced_motion: ReducedMotion
    sound_enabled: bool
    questions_asked: bool
    # Set once every question was answered, `unknown` included (decision 63); null until then.
    profile_completed_at: datetime | None
    consent_version: str | None
    updated_at: datetime


class ProfilePatch(BaseModel):
    """
    The fields a user may change, any of them, alone.

    The three consent switches are not here: they change only through
    `POST /consents`, which records the answer. A field sent as null is refused;
    to clear an answer, send `unknown` (or `[]` for the goals).

    Skipping the optional questions is `questions_asked: true` alone: every
    field stays `unknown` and the questions are never offered again. Answering
    any of the three question fields records the same.

    `complete_profile: true` completes the profile (decision 63) and needs an explicit answer
    to every question in the same body: `goals` (`[]` is «أفضّل عدم الإجابة»),
    `knowledge_level`, `age_range`, `religious_background` and `gender` (`unknown` is that
    answer). A body that leaves one out is a 422.
    """

    model_config = ConfigDict(extra="forbid")

    goals: Annotated[list[Goal], Field(max_length=len(Goal))] | None = None
    knowledge_level: KnowledgeLevel | None = None
    age_range: AgeRange | None = None
    religious_background: ReligiousBackground | None = None
    gender: Gender | None = None
    language: Annotated[str, Field(max_length=LANGUAGE_MAX)] | None = None
    theme: Theme | None = None
    reduced_motion: ReducedMotion | None = None
    sound_enabled: bool | None = None
    questions_asked: bool | None = None
    complete_profile: Literal[True] | None = None

    @field_validator("goals")
    @classmethod
    def _unique_goals(cls, value: list[Goal] | None) -> list[Goal] | None:
        # Keep the order the user gave, drop repeats.
        return None if value is None else list(dict.fromkeys(value))

    @field_validator("language")
    @classmethod
    def _language_tag(cls, value: str | None) -> str | None:
        if value is not None and not _LANGUAGE.match(value):
            message = "must be a language tag such as ar or en-GB"
            raise ValueError(message)
        return value

    @model_validator(mode="after")
    def _complete_means_all_answered(self) -> Self:
        if self.complete_profile:
            missing = sorted(COMPLETION_FIELDS - self.model_fields_set)
            if missing:
                message = f"complete_profile needs an explicit answer for {', '.join(missing)}"
                raise ValueError(message)
        return self

    @model_validator(mode="after")
    def _no_nulls(self) -> Self:
        nulled = sorted(name for name in self.model_fields_set if getattr(self, name) is None)
        if nulled:
            message = (
                f"null is not allowed for {', '.join(nulled)}; send unknown to clear an answer"
            )
            raise ValueError(message)
        return self


class ConsentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ConsentKind
    # The version of the text the user saw when they answered.
    version: Version
    granted: bool


class ConsentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: ConsentKind
    version: str
    granted: bool
    created_at: datetime
