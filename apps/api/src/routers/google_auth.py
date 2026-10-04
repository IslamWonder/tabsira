"""
Google sign-in: `GET /auth/google/start`, then Google, then `GET /auth/google/callback`.

Both are browser navigations, not API calls, so they answer with redirects.
Success lands on the web app (the `next` path given to `start`, or `/`); every
failure lands on `{SITE_URL}/signin?error=<code>` with one of:

- `google_state`: the sign-in is unknown, expired, used already, or was not
  started by this browser.
- `google_denied`: the person declined at Google.
- `google_failed`: Google's answer could not be completed or trusted.
- `account_disabled`: the account behind the identity is disabled.

When GOOGLE_CLIENT_ID is empty both routes answer 503 GOOGLE_NOT_CONFIGURED.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from src.config import Settings
from src.deps import DbDep, GoogleDep, IpHashDep, SettingsDep
from src.errors import AppError, ErrorCode
from src.models.login_attempt import AttemptKind
from src.services import auth_service, google_oidc, oauth_state_service, rate_limit, session_service
from src.services.google_oidc import OidcError

log = logging.getLogger("tabsira.google")

router = APIRouter(prefix="/auth/google", tags=["auth"])

# Ties a started sign-in to the browser that started it. Host-only on the API
# and limited to these routes; SameSite=Lax still travels on Google's top-level redirect back.
BINDER_COOKIE = "__Secure-tabsira_oauth"
BINDER_PATH = "/auth/google"
NOT_CONFIGURED = AppError(
    ErrorCode.GOOGLE_NOT_CONFIGURED, "Google sign-in is not configured.", status_code=503
)

WEB_STATE = "google_state"
WEB_DENIED = "google_denied"


def _require_configured(settings: Settings) -> None:
    if not settings.google_configured:
        raise NOT_CONFIGURED


def _failure(settings: Settings, code: str) -> RedirectResponse:
    redirect = RedirectResponse(
        f"{settings.site_url}/signin?error={code}", status_code=status.HTTP_302_FOUND
    )
    _clear_binder(redirect)
    return redirect


def _clear_binder(response: Response) -> None:
    response.delete_cookie(
        BINDER_COOKIE, path=BINDER_PATH, secure=True, httponly=True, samesite="lax"
    )


@router.get(
    "/start",
    status_code=status.HTTP_302_FOUND,
    response_class=RedirectResponse,
    summary="Send the browser to Google to sign in",
)
async def start(
    db: DbDep,
    settings: SettingsDep,
    ip_hash: IpHashDep,
    next_path: Annotated[
        str | None,
        Query(
            alias="next",
            max_length=oauth_state_service.NEXT_PATH_MAX,
            description="A path in the web app to return to; anything else is ignored.",
        ),
    ] = None,
) -> RedirectResponse:
    """
    Begin the authorization code flow with PKCE (S256), a state and a nonce.

    Redirects to Google. The state, the code verifier and the nonce are kept on
    the server for GOOGLE_STATE_TTL_SECONDS; a cookie ties them to this browser.
    """
    _require_configured(settings)
    await rate_limit.check(db, settings, AttemptKind.GOOGLE_START, ip_hash=ip_hash)
    await rate_limit.record(db, settings, AttemptKind.GOOGLE_START, ip_hash=ip_hash, succeeded=True)
    flow = await oauth_state_service.start(db, settings, next_path)
    await db.commit()
    redirect = RedirectResponse(
        google_oidc.authorization_url(
            settings, state=flow.state, nonce=flow.nonce, verifier=flow.verifier
        ),
        status_code=status.HTTP_302_FOUND,
    )
    redirect.set_cookie(
        BINDER_COOKIE,
        flow.binder,
        max_age=settings.google_state_ttl_seconds,
        path=BINDER_PATH,
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return redirect


@router.get(
    "/callback",
    status_code=status.HTTP_302_FOUND,
    response_class=RedirectResponse,
    summary="Where Google sends the browser back",
)
async def callback(
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    ip_hash: IpHashDep,
    oidc: GoogleDep,
    code: Annotated[str | None, Query(max_length=2048)] = None,
    state: Annotated[str | None, Query(max_length=256)] = None,
    error: Annotated[str | None, Query(max_length=256)] = None,
) -> RedirectResponse:
    """
    Finish the sign-in: check the state, exchange the code, validate the ID token.

    Then link or create the account, start a session and redirect to the web app.
    """
    _require_configured(settings)
    flow = (
        await oauth_state_service.consume(db, state, request.cookies.get(BINDER_COOKIE))
        if state
        else None
    )
    await db.commit()
    if flow is None:
        return _failure(settings, WEB_STATE)
    if error is not None or not code:
        return _failure(
            settings, WEB_DENIED if error == "access_denied" else auth_service.WEB_GOOGLE_FAILED
        )
    try:
        id_token = await oidc.exchange_code(code, flow.verifier)
        identity = await oidc.verify_id_token(id_token, nonce=flow.nonce)
    except OidcError as refusal:
        log.warning("Google sign-in refused: %s", refusal)
        return _failure(settings, auth_service.WEB_GOOGLE_FAILED)
    try:
        user = await auth_service.sign_in_with_google(db, identity)
    except auth_service.SignInRefusedError as refusal:
        return _failure(settings, refusal.code)
    token = await session_service.start_for_request(
        db, settings, request, user_id=user.id, ip_hash=ip_hash
    )
    await db.commit()
    redirect = RedirectResponse(
        f"{settings.site_url}{flow.next_path or '/'}", status_code=status.HTTP_302_FOUND
    )
    session_service.set_cookie(redirect, settings, token)
    _clear_binder(redirect)
    return redirect
