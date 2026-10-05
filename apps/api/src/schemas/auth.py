"""Request and response bodies of the account routes."""

from __future__ import annotations

import re
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
# A version label such as "2026-10-04"; the column that stores it holds 32 characters.
LegalVersion = Annotated[str, StringConstraints(min_length=1, max_length=32)]


# An address or a link in a name would put a stranger's contact details on a public page.
_NAME_FORBIDDEN = re.compile(r"[@<>]|https?:|www\.", re.IGNORECASE)


def _clean_display_name(value: str) -> str:
    """
    Strip a name and refuse control and format characters (newlines, bidi tricks).

    The name is the person's real full name, which may be shown publicly, so an address or a
    link in it is refused as well.
    """
    name = " ".join(value.split())
    if not name or any(unicodedata.category(char) in {"Cc", "Cf", "Cs", "Co"} for char in name):
        message = "must be text without control characters"
        raise ValueError(message)
    if _NAME_FORBIDDEN.search(name):
        message = "must not contain an address or a link"
        raise ValueError(message)
    return name


def checked_display_name(value: str) -> str:
    """Clean the person's full name and bound it."""
    name = _clean_display_name(value)
    if len(name) > DISPLAY_NAME_MAX:
        message = f"must have at most {DISPLAY_NAME_MAX} characters"
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
    # The versions of the terms of use and the privacy policy the person ticked. They must be
    # the current ones (decision 35); the check answers `legal_acceptance_required`.
    accepted_terms_version: LegalVersion
    accepted_privacy_version: LegalVersion
    # The separate, unticked box «أوافق على ظهور اسمي الكامل مع منشوراتي» (decision 64): the
    # display name is the person's real full name, shown publicly only while this is true.
    public_full_name: bool = False

    _password = field_validator("password")(_checked_password)
    _display_name = field_validator("display_name")(checked_display_name)


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
    # True when the latest accepted terms or privacy version is not the current one, or there is
    # none: the web app then asks for the acceptance (`POST /auth/legal/accept`) before going on.
    legal_acceptance_required: bool
    # False until the whole profile was answered (decision 64): the web app then shows the
    # profile form before anything else, and the scan and the chat answer `profile_required`.
    profile_completed: bool
    # Whether the full name may be shown beside the handle on public pages.
    public_full_name: bool


class LegalAcceptIn(BaseModel):
    """The versions a signed-in person accepts; they must be the current ones."""

    model_config = ConfigDict(extra="forbid")

    terms_version: LegalVersion
    privacy_version: LegalVersion
    # A Google account arrives with the name Google holds: here the person gives their real full
    # name, and says whether it may be shown (true or false is a recorded answer; absent leaves
    # the choice as it is).
    display_name: Annotated[str, Field(min_length=1, max_length=DISPLAY_NAME_MAX * 2)] | None = None
    public_full_name: bool | None = None

    @field_validator("display_name")
    @classmethod
    def _display_name(cls, value: str | None) -> str | None:
        return None if value is None else checked_display_name(value)


class ProviderOut(BaseModel):
    id: Literal["password", "google"]
    available: bool


class ProvidersOut(BaseModel):
    providers: list[ProviderOut]


class StatusOut(BaseModel):
    """The answer of the routes that report only that they did what was asked."""

    status: Literal["ok", "accepted"]
