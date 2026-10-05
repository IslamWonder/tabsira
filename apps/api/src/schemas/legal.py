"""The versions of the legal texts and the privacy address they name."""

from __future__ import annotations

from pydantic import BaseModel


class LegalOut(BaseModel):
    """What the sign-up page, the terms page and the privacy page need to show and to send back."""

    terms_version: str
    privacy_version: str
    # The support address is never shown: the support form is the way in.
    privacy_email: str
