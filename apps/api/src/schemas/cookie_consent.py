"""The cookie-consent routes: the choice a visitor sends, the choice in force, and the policy."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

PolicyVersion = Field(default=None, max_length=32, pattern=r"^[A-Za-z0-9._-]+$")


class ConsentCategories(BaseModel):
    """Each category and whether it is on. The necessary one always is."""

    necessary: Literal[True] = True
    analytics: bool
    behaviour: bool


class CookieConsentIn(BaseModel):
    """
    A choice, as the visitor made it.

    `consent_id` is the id the server gave this browser before; leave it out on the first
    choice. An id the server does not know is not adopted: a new one is made and returned.
    `policy_version` is the version of the text the visitor was shown; leave it out for the
    current one. The two flags must be JSON booleans.
    """

    model_config = ConfigDict(extra="ignore")

    consent_id: uuid.UUID | None = None
    policy_version: str | None = PolicyVersion
    necessary: Literal[True] = True
    analytics: StrictBool
    behaviour: StrictBool


class CookieConsentOut(BaseModel):
    """
    The choice in force for one consent id.

    `categories` is what may run now: the recorded choice while it holds, and only the
    necessary category once it lapsed. It lapses when the policy version changed or
    `expires_at` has passed; `reask` is then true and the visitor must be asked again.
    """

    consent_id: uuid.UUID
    policy_version: str
    decided_at: datetime
    expires_at: datetime
    reask: bool
    categories: ConsentCategories


class ConsentCategoryOut(BaseModel):
    key: Literal["necessary", "analytics", "behaviour"]
    # The necessary category cannot be refused; the others are chosen separately.
    required: bool
    title: str
    description: str


class ConsentPolicyOut(BaseModel):
    """What a visitor is asked, and when they are asked again."""

    policy_version: str
    reask_days: int
    categories: list[ConsentCategoryOut]
