"""Sign up, sign in, sign out and who am I."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Request, Response, status

from src.deps import DbDep, HumanDep, IpHashDep, SettingsDep, UngatedCurrentUser
from src.models.email_token import TokenPurpose
from src.schemas.auth import LegalAcceptIn, LoginIn, ProviderOut, ProvidersOut, SignupIn, UserOut
from src.services import (
    auth_service,
    email_service,
    email_token_service,
    legal_service,
    session_service,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/signup",
    dependencies=[HumanDep],
    status_code=status.HTTP_201_CREATED,
    summary="Create an account with an e-mail address and a password",
)
async def signup(
    body: SignupIn,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    db: DbDep,
    settings: SettingsDep,
    ip_hash: IpHashDep,
) -> UserOut:
    """
    Create the account, sign it in, and mail a verification link.

    The new account can be used at once; its address stays unverified until the
    link is followed. Rate limited per IP and per e-mail address. A mail that
    cannot be sent never fails the sign-up.
    """
    user = await auth_service.signup(
        db,
        settings,
        email=body.email,
        password=body.password,
        display_name=body.display_name,
        ip_hash=ip_hash,
        accepted_terms_version=body.accepted_terms_version,
        accepted_privacy_version=body.accepted_privacy_version,
        public_full_name=body.public_full_name,
    )
    token = await session_service.start_for_request(
        db, settings, request, user_id=user.id, ip_hash=ip_hash
    )
    verification = await email_token_service.issue(db, settings, user, TokenPurpose.VERIFY_EMAIL)
    await db.commit()
    session_service.set_cookie(response, settings, token)
    background.add_task(
        email_service.send_email_verification,
        settings,
        email=user.email,
        name=user.display_name,
        token=verification,
    )
    return await auth_service.describe(db, settings, user)


@router.post(
    "/login",
    summary="Sign in with an e-mail address and a password",
    dependencies=[HumanDep],
)
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
    ip_hash: IpHashDep,
) -> UserOut:
    """
    Start a session.

    A wrong address and a wrong password answer the same 401. Rate limited per IP
    and per e-mail address, counting failed attempts, before the password is checked.
    """
    user = await auth_service.login(
        db, settings, email=body.email, password=body.password, ip_hash=ip_hash
    )
    token = await session_service.start_for_request(
        db, settings, request, user_id=user.id, ip_hash=ip_hash
    )
    await db.commit()
    session_service.set_cookie(response, settings, token)
    return await auth_service.describe(db, settings, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="End the current session")
async def logout(request: Request, db: DbDep, settings: SettingsDep) -> Response:
    """End the session and clear the cookie. Safe to repeat, and to call with no session."""
    token = session_service.cookie_token(request, settings)
    if token is not None:
        await session_service.revoke(db, token)
        await db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    session_service.clear_cookie(response, settings)
    return response


@router.get("/me", summary="The signed-in account")
async def me(user: UngatedCurrentUser, db: DbDep, settings: SettingsDep) -> UserOut:
    """Return the caller's own account. The private profile fields are not part of it."""
    return await auth_service.describe(db, settings, user)


@router.post("/legal/accept", summary="Accept the current terms of use and privacy policy")
async def accept_legal(
    body: LegalAcceptIn, user: UngatedCurrentUser, db: DbDep, settings: SettingsDep
) -> UserOut:
    """
    Record that the signed-in account accepts both texts, for a version that changed.

    The versions must be the current ones (`GET /legal`); anything else is a 422
    `legal_acceptance_required`. Two consent rows are appended; none is ever edited. It also
    takes, for a Google account, the real full name (`display_name`) and the answer to the
    `public_full_name` consent (decision 63); both are optional.
    """
    legal_service.require_current(settings, body.terms_version, body.privacy_version)
    legal_service.record_acceptance(db, settings, user.id)
    await auth_service.record_name_choices(
        db, settings, user, display_name=body.display_name, public_full_name=body.public_full_name
    )
    await db.commit()
    return await auth_service.describe(db, settings, user)


@router.get("/providers", summary="Which ways of signing in are available")
async def providers(settings: SettingsDep) -> ProvidersOut:
    """Whether password and Google sign-in can be used, for the sign-in page to show."""
    return ProvidersOut(
        providers=[
            ProviderOut(id="password", available=True),
            ProviderOut(id="google", available=settings.google_configured),
        ]
    )
