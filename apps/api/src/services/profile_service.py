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

from src import clock
from src.errors import AppError, ErrorCode
from src.models.consent import Consent, ConsentKind
from src.models.profile import AgeRange, Profile
from src.models.user import User
from src.schemas.profile import ProfilePatch
from src.services import legal_service, photo_service
from src.storage.base import StorageError
from src.storage.photos import PhotoStore

# The version recorded when the profile itself withdraws a consent and no
# version of the text is known to it.
UNVERSIONED = "unversioned"

# The fields of the three optional questions (master prompt v2 §5), in their order.
QUESTION_FIELDS = frozenset({"goals", "knowledge_level", "age_range"})


async def ensure_profile(db: AsyncSession, user_id: uuid.UUID) -> Profile:
    """Return the user's profile, creating the empty one if there is none yet."""
    await db.execute(insert(Profile).values(user_id=user_id).on_conflict_do_nothing())
    return (await db.scalars(select(Profile).where(Profile.user_id == user_id))).one()


async def record_consent(
    db: AsyncSession,
    user_id: uuid.UUID,
    kind: ConsentKind,
    version: str,
    *,
    granted: bool,
    photos: PhotoStore | None = None,
) -> Consent:
    """
    Append one answer to the consent history and update the profile's mirror of it.

    A user who declared they are under 13 cannot consent to photo storage
    (master prompt v2, section 5): their photos are never kept on the server.
    Withdrawing the photo consent deletes every photo kept so far, both copies, from
    `photos` before the answer is recorded; a store that cannot be reached refuses the
    withdrawal with 503, so a recorded withdrawal always means the photos are gone.
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
    if kind == ConsentKind.PUBLIC_FULL_NAME and granted and profile.age_range == AgeRange.UNDER_13:
        raise AppError(
            ErrorCode.CONSENT_NOT_ALLOWED,
            "The full name of an account under 13 is never shown.",
            status_code=403,
        )
    if kind == ConsentKind.PHOTO_STORAGE and not granted and photos is not None:
        await _forget_photos(db, user_id, photos)
    consent = Consent(user_id=user_id, kind=kind, version=version, granted=granted)
    db.add(consent)
    if kind == ConsentKind.PHOTO_STORAGE:
        profile.photo_storage_consent = granted
    elif kind == ConsentKind.PERSONALIZATION:
        profile.personalization_enabled = granted
    elif kind == ConsentKind.PUBLIC_FULL_NAME:
        # The mirror public answers read lives on the account, next to the handle.
        user = await db.get_one(User, user_id)
        user.public_full_name = granted
    else:  # memory: the legal kinds were refused above
        profile.memory_enabled = granted
    profile.consent_version = version
    await db.flush()
    return consent


async def _forget_photos(db: AsyncSession, user_id: uuid.UUID, photos: PhotoStore) -> None:
    try:
        await photo_service.remove_all(db, photos, user_id)
    except StorageError:
        raise AppError(
            ErrorCode.STORAGE_UNAVAILABLE,
            "The kept photos could not be deleted, so the consent stays as it was. Try again.",
            status_code=503,
        ) from None


async def update_profile(
    db: AsyncSession, user_id: uuid.UUID, patch: ProfilePatch, *, photos: PhotoStore | None = None
) -> Profile:
    """Apply the fields the patch carries and no others; `photos` is for a withdrawn consent."""
    profile = await ensure_profile(db, user_id)
    changes = patch.model_dump(exclude_unset=True)
    complete = changes.pop("complete_profile", None)
    if "goals" in changes:
        profile.goals = [goal.value for goal in changes.pop("goals")]
    for field, value in changes.items():
        setattr(profile, field, value)
    if changes.keys() & QUESTION_FIELDS or "goals" in patch.model_fields_set:
        # An answer, or a skip to `unknown`, means the questions were offered.
        profile.questions_asked = True
    if complete:
        # The first completion stays the date; later edits do not move it.
        profile.questions_asked = True
        if profile.profile_completed_at is None:
            profile.profile_completed_at = clock.utcnow()
    if profile.age_range == AgeRange.UNDER_13 and profile.photo_storage_consent:
        # Declaring under 13 withdraws the photo consent, on the record.
        await record_consent(
            db,
            user_id,
            ConsentKind.PHOTO_STORAGE,
            profile.consent_version or UNVERSIONED,
            granted=False,
            photos=photos,
        )
    if profile.age_range == AgeRange.UNDER_13 and await _shows_full_name(db, user_id):
        # Declaring under 13 withdraws the consent to show the full name, on the record.
        await record_consent(
            db,
            user_id,
            ConsentKind.PUBLIC_FULL_NAME,
            profile.consent_version or UNVERSIONED,
            granted=False,
        )
    await db.flush()
    return profile


async def _shows_full_name(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return bool(await db.scalar(select(User.public_full_name).where(User.id == user_id)))


async def require_completed(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Answer 403 `profile_required` unless the account completed its profile (decision 63)."""
    completed_at = await db.scalar(
        select(Profile.profile_completed_at).where(Profile.user_id == user_id)
    )
    if completed_at is None:
        raise AppError(
            ErrorCode.profile_required,
            "Complete your profile first.",
            status_code=403,
        )
