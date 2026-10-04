"""The export of everything an account owns."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from src.schemas.cookie_consent import CookieConsentExport
from src.schemas.profile import ConsentOut, ProfileOut


class UserExport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
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
