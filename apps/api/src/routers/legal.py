"""
The current versions of the terms of use and the privacy policy, and the contact addresses.

Public: the sign-up page reads it before there is a session, and sends the versions back as
the ones the person accepted.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from src.deps import SettingsDep
from src.schemas.legal import LegalOut

router = APIRouter(prefix="/legal", tags=["legal"])

# Nothing in it is about a person, so it may be cached; five minutes keeps a new version
# from waiting long to be asked for.
CACHE_CONTROL = "public, max-age=300"


@router.get("", summary="Current legal versions and contact addresses")
async def get_legal(settings: SettingsDep, response: Response) -> LegalOut:
    """Return the versions a sign-up must accept, and the addresses the legal pages name."""
    response.headers["Cache-Control"] = CACHE_CONTROL
    return LegalOut(
        terms_version=settings.terms_version,
        privacy_version=settings.privacy_version,
        privacy_email=settings.privacy_email,
        support_email=settings.support_email,
    )
