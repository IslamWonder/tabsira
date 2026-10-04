"""
The optional profile and the consent records.

The profile holds what a user chose to say about themselves, `unknown` for
everything they did not. It changes how an explanation is worded and which of
several valid texts is chosen, never the text or the truth of a link.

The three consent switches (photo storage, personalization, memory) are
mirrors of the latest row of their kind in `consents`, and change only through
`record_consent`, so the history and the current state cannot disagree.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors import AppError, ErrorCode
from src.models.consent import Consent, ConsentKind
from src.models.profile import AgeRange, Profile
from src.schemas.profile import ProfilePatch
from src.services import legal_service

# The version recorded when the profile itself withdraws a consent and no
# version of the text is known to it.
UNVERSIONED = "unversioned"


async def ensure_profile(db: AsyncSession, user_id: uuid.UUID) -> Profile:
    """Return the user's profile, creating the empty one if there is none yet."""
    await db.execute(insert(Profile).values(user_id=user_id).on_conflict_do_nothing())
    return (await db.scalars(select(Profile).where(Profile.user_id == user_id))).one()


async def record_consent(
    db: AsyncSession, user_id: uuid.UUID, kind: ConsentKind, version: str, *, granted: bool
) -> Consent:
    """
    Append one answer to the consent history and update the profile's mirror of it.

    A user who declared they are under 13 cannot consent to photo storage
    (master prompt v2, section 5): their photos are never kept on the server.
    """
    if kind in legal_service.LEGAL_KINDS:
        raise AppError(
            ErrorCode.CONSENT_NOT_ALLOWED,
            "The terms and the privacy policy are accepted at sign-up or through "
            "POST /auth/legal/accept, not as a consent switch.",
            status_code=403,
        )
    profile = await ensure_profile(db, user_id)
    if kind == ConsentKind.PHOTO_STORAGE and granted and profile.age_range == AgeRange.UNDER_13:
        raise AppError(
            ErrorCode.CONSENT_NOT_ALLOWED,
            "Photos of users under 13 are not stored.",
            status_code=403,
        )
    consent = Consent(user_id=user_id, kind=kind, version=version, granted=granted)
    db.add(consent)
    if kind == ConsentKind.PHOTO_STORAGE:
        profile.photo_storage_consent = granted
    elif kind == ConsentKind.PERSONALIZATION:
        profile.personalization_enabled = granted
    elif kind == ConsentKind.MEMORY:
        profile.memory_enabled = granted
    profile.consent_version = version
    await db.flush()
    return consent


async def update_profile(db: AsyncSession, user_id: uuid.UUID, patch: ProfilePatch) -> Profile:
    """Apply the fields the patch carries and no others."""
    profile = await ensure_profile(db, user_id)
    changes = patch.model_dump(exclude_unset=True)
    if "goals" in changes:
        profile.goals = [goal.value for goal in changes.pop("goals")]
    for field, value in changes.items():
        setattr(profile, field, value)
    if profile.age_range == AgeRange.UNDER_13 and profile.photo_storage_consent:
        # Declaring under 13 withdraws the photo consent, on the record.
        await record_consent(
            db,
            user_id,
            ConsentKind.PHOTO_STORAGE,
            profile.consent_version or UNVERSIONED,
            granted=False,
        )
    await db.flush()
    return profile
