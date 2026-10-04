"""Sign up, sign in, sign out and who am I."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Request, Response, status

from src.deps import CurrentUser, DbDep, IpHashDep, SettingsDep
from src.models.email_token import TokenPurpose
from src.schemas.auth import LoginIn, ProviderOut, ProvidersOut, SignupIn, UserOut
from src.services import auth_service, email_service, email_token_service, session_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/signup",
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
    return await auth_service.describe(db, user)


@router.post("/login", summary="Sign in with an e-mail address and a password")
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
    return await auth_service.describe(db, user)


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
async def me(user: CurrentUser, db: DbDep) -> UserOut:
    """Return the caller's own account. The private profile fields are not part of it."""
    return await auth_service.describe(db, user)


@router.get("/providers", summary="Which ways of signing in are available")
async def providers(settings: SettingsDep) -> ProvidersOut:
    """Whether password and Google sign-in can be used, for the sign-in page to show."""
    return ProvidersOut(
        providers=[
            ProviderOut(id="password", available=True),
            ProviderOut(id="google", available=settings.google_configured),
        ]
    )
