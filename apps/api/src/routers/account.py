"""Owning an account: exporting everything it holds, and deleting it."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from src.deps import DbDep, PhotoStoreDep, SettingsDep, UngatedCurrentUser, UngatedOptionalUser
from src.scans.deps import RedisDep
from src.schemas.account import AccountExport
from src.services import account_service, session_service

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/export", summary="Download everything the account owns")
async def export_account(user: UngatedCurrentUser, db: DbDep, response: Response) -> AccountExport:
    """Return the account, its profile, consents, identities, sessions and learning as JSON."""
    response.headers["Content-Disposition"] = 'attachment; filename="tabsira-export.json"'
    return await account_service.export_account(db, user)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete the account and everything it owns",
)
async def delete_account(
    user: UngatedOptionalUser,
    db: DbDep,
    settings: SettingsDep,
    redis: RedisDep,
    photos: PhotoStoreDep,
) -> Response:
    """
    Delete the user, their profile, consents, identities, sessions, photos and everything they saved.

    Idempotent: without a valid session there is nothing left to delete, and the
    answer is the same 204 that clears the cookie. 503 STORAGE_UNAVAILABLE, with nothing
    deleted, when the photo store cannot be reached.
    """
    if user is not None:
        await account_service.delete_account(db, user, redis=redis, photos=photos)
        await db.commit()
        await account_service.sweep_after_deletion(photos, user.id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    session_service.clear_cookie(response, settings)
    return response
