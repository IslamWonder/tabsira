"""Request and response bodies of the account routes."""

from __future__ import annotations

import unicodedata
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from src import security

DISPLAY_NAME_MAX = 60
# Tokens are 256 random bits in URL-safe text (43 characters); the bound only
# refuses absurd input before it is hashed.
Token = Annotated[str, StringConstraints(min_length=16, max_length=256)]


def _clean_display_name(value: str) -> str:
    """Strip a display name and refuse control and format characters (newlines, bidi tricks)."""
    name = " ".join(value.split())
    if not name or any(unicodedata.category(char) in {"Cc", "Cf", "Cs", "Co"} for char in name):
        message = "must be text without control characters"
        raise ValueError(message)
    return name


def _checked_password(value: str) -> str:
    problem = security.password_problem(value)
    if problem is not None:
        raise ValueError(problem)
    return value


class SignupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str
    display_name: Annotated[str, Field(min_length=1, max_length=DISPLAY_NAME_MAX * 2)]

    _password = field_validator("password")(_checked_password)

    @field_validator("display_name")
    @classmethod
    def _display_name(cls, value: str) -> str:
        name = _clean_display_name(value)
        if len(name) > DISPLAY_NAME_MAX:
            message = f"must have at most {DISPLAY_NAME_MAX} characters"
            raise ValueError(message)
        return name


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    # Not held to the sign-up rules: a wrong password is a wrong password, not a format error.
    password: Annotated[str, Field(min_length=1, max_length=1024)]


class EmailIn(BaseModel):
    """An address, for the routes that mail a link to it."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class VerifyEmailIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: Token


class ResetPasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: Token
    password: str

    _password = field_validator("password")(_checked_password)


class UserOut(BaseModel):
    """The signed-in user's own account. Nothing of the private profile is here."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    is_admin: bool
    # An unverified address can sign in, but may not publish anything public.
    email_verified: bool
    has_password: bool
    providers: list[str]
    created_at: datetime


class ProviderOut(BaseModel):
    id: Literal["password", "google"]
    available: bool


class ProvidersOut(BaseModel):
    providers: list[ProviderOut]


class StatusOut(BaseModel):
    """The answer of the routes that report only that they did what was asked."""

    status: Literal["ok", "accepted"]
