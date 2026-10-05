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

# A browser or a proxy may keep it but must ask again before using it: a new version has to
# reach the sign-up page at once, and a sign-up that carries an old one is refused.
CACHE_CONTROL = "no-cache"


@router.get("", summary="Current legal versions and contact addresses")
async def get_legal(settings: SettingsDep, response: Response) -> LegalOut:
    """Return the versions a sign-up must accept, and the addresses the legal pages name."""
    response.headers["Cache-Control"] = CACHE_CONTROL
    return LegalOut(
        terms_version=settings.terms_version,
        privacy_version=settings.privacy_version,
        privacy_email=settings.privacy_email,
    )
