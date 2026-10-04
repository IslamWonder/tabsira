"""The optional profile and the consent records. Every route needs a session."""

from __future__ import annotations

from fastapi import APIRouter, status

from src.deps import CurrentUser, DbDep, PhotoStoreDep
from src.schemas.profile import ConsentIn, ConsentOut, ProfileOut, ProfilePatch
from src.services import profile_service

router = APIRouter(tags=["profile"])


@router.get("/profile", summary="The caller's profile")
async def get_profile(user: CurrentUser, db: DbDep) -> ProfileOut:
    """
    Return the caller's own profile, empty answers as `unknown`.

    The religious background, the gender and the age range are private: this
    route and the account export are the only places they are ever returned.
    """
    profile = await profile_service.ensure_profile(db, user.id)
    await db.commit()
    return ProfileOut.model_validate(profile)


@router.patch("/profile", summary="Change some answers of the caller's profile")
async def patch_profile(
    body: ProfilePatch, user: CurrentUser, db: DbDep, photos: PhotoStoreDep
) -> ProfileOut:
    """
    Change the fields sent and no others.

    Enums are validated; a null is refused (send `unknown` to clear an answer).
    The three consent switches change through `POST /consents` only; declaring under 13
    withdraws the photo consent and deletes the kept photos (503 when the store is down).
    """
    profile = await profile_service.update_profile(db, user.id, body, photos=photos)
    await db.commit()
    return ProfileOut.model_validate(profile)


@router.post(
    "/consents",
    status_code=status.HTTP_201_CREATED,
    summary="Record an answer to a consent question",
)
async def post_consent(
    body: ConsentIn, user: CurrentUser, db: DbDep, photos: PhotoStoreDep
) -> ConsentOut:
    """
    Append the answer to the user's consent history, and update the matching switch.

    A consent is withdrawn by recording the same kind with `granted` false. The
    history is never edited. Withdrawing the photo consent deletes the kept photos
    first; 503 STORAGE_UNAVAILABLE, with nothing recorded, when the store is down.
    """
    consent = await profile_service.record_consent(
        db, user.id, body.kind, body.version, granted=body.granted, photos=photos
    )
    await db.commit()
    return ConsentOut.model_validate(consent)
