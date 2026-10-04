"""Shared FastAPI dependencies: settings, the database, and who is calling."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings
from src.database import get_db
from src.errors import AppError, ErrorCode
from src.models.user import User
from src.services import auth_service, session_service
from src.services.google_oidc import GoogleOidc


def get_app_settings(request: Request) -> Settings:
    """Return the settings the running application was built with."""
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
DbDep = Annotated[AsyncSession, Depends(get_db)]


def get_ip_hash(request: Request, settings: SettingsDep) -> str:
    """Return the keyed hash of the caller's address. The address itself is never kept."""
    return auth_service.hash_ip(settings, request.client.host if request.client else None)


IpHashDep = Annotated[str, Depends(get_ip_hash)]


def get_google_oidc(request: Request, settings: SettingsDep) -> GoogleOidc:
    """Return the process's Google client, built on first use so its key cache is shared."""
    client: GoogleOidc | None = getattr(request.app.state, "google_oidc", None)
    if client is None:
        client = GoogleOidc(settings)
        request.app.state.google_oidc = client
    return client


GoogleDep = Annotated[GoogleOidc, Depends(get_google_oidc)]


async def optional_user(request: Request, db: DbDep, settings: SettingsDep) -> User | None:
    """
    Return the signed-in user, or None for a guest.

    Signed in means: the session cookie hashes to an unexpired session of an
    account that is active and not deleted. Knowing a user's id grants nothing;
    a route that needs an owner checks the owner against this user.
    """
    token = session_service.cookie_token(request, settings)
    if token is None:
        return None
    found = await session_service.find(db, token)
    if found is None:
        return None
    session, user = found
    if await session_service.touch(db, session):
        await db.commit()
    return user


OptionalUser = Annotated[User | None, Depends(optional_user)]


async def current_user(user: OptionalUser) -> User:
    """Return the signed-in user, or answer 401."""
    if user is None:
        raise AppError(ErrorCode.UNAUTHORIZED, "Sign in first.", status_code=401)
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def verified_user(user: CurrentUser) -> User:
    """
    Return the signed-in user, who must have a verified e-mail address.

    Every route that publishes anything public depends on this: an unverified
    address can sign in and use the app, but is a throwaway until it proves itself.
    """
    if user.email_verified_at is None:
        raise AppError(
            ErrorCode.EMAIL_NOT_VERIFIED,
            "Verify your e-mail address first.",
            status_code=403,
        )
    return user


VerifiedUser = Annotated[User, Depends(verified_user)]
