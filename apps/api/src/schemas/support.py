"""The support form's body."""

from __future__ import annotations

import unicodedata
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

NAME_MAX = 80
MESSAGE_MIN = 20
MESSAGE_MAX = 4000


class SupportTopic(StrEnum):
    ACCOUNT = "account"
    PRIVACY = "privacy"
    BUG = "bug"
    CONTENT = "content"
    SUGGESTION = "suggestion"
    OTHER = "other"


class SupportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Used as Reply-To only; EmailStr refuses line breaks, so it cannot inject a header.
    email: EmailStr
    name: Annotated[str | None, Field(max_length=NAME_MAX * 2)] = None
    topic: SupportTopic
    message: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=MESSAGE_MIN, max_length=MESSAGE_MAX),
    ]
    # A field no person sees: a bot that fills it is answered 202 and nothing is sent.
    website: Annotated[str | None, Field(max_length=500)] = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = " ".join(value.split())
        if any(unicodedata.category(char) in {"Cc", "Cf", "Cs", "Co"} for char in name):
            message = "must be text without control characters"
            raise ValueError(message)
        if len(name) > NAME_MAX:
            message = f"must have at most {NAME_MAX} characters"
            raise ValueError(message)
        return name or None
