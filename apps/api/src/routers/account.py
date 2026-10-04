"""Owning an account: exporting everything it holds, and deleting it."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from src.deps import DbDep, SettingsDep, UngatedCurrentUser, UngatedOptionalUser
from src.schemas.account import AccountExport
from src.services import account_service, session_service

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/export", summary="Download everything the account owns")
async def export_account(user: UngatedCurrentUser, db: DbDep, response: Response) -> AccountExport:
    """Return the account, its profile, consents, linked identities and sessions as JSON."""
    response.headers["Content-Disposition"] = 'attachment; filename="tabsira-export.json"'
    return await account_service.export_account(db, user)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete the account and everything it owns",
)
async def delete_account(user: UngatedOptionalUser, db: DbDep, settings: SettingsDep) -> Response:
    """
    Delete the user, their profile, consents, linked identities and every session.

    Idempotent: without a valid session there is nothing left to delete, and the
    answer is the same 204 that clears the cookie.
    """
    if user is not None:
        await account_service.delete_account(db, user)
        await db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    session_service.clear_cookie(response, settings)
    return response
