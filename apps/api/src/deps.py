"""Shared FastAPI dependencies: settings, the database, and who is calling."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings
from src.database import get_db
from src.errors import AppError, ErrorCode
from src.features import FeatureFlag
from src.messages import messages_for
from src.models.user import User
from src.services import auth_service, legal_service, session_service, turnstile_service
from src.services.google_oidc import GoogleOidc
from src.services.insight_source import InsightSource
from src.services.moderation_guard import OpenAiTextGuard, TextGuard
from src.services.social_limits import WriteKind, get_social_limits
from src.services.window_limiter import too_many_requests
from src.storage.photos import PhotoStore, build_photo_store


def get_app_settings(request: Request) -> Settings:
    """Return the settings the running application was built with."""
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
DbDep = Annotated[AsyncSession, Depends(get_db)]


async def require_human(request: Request, settings: SettingsDep) -> None:
    """
    Answer 403 `turnstile_failed` unless the request carries a token Cloudflare accepts.

    Attached with `dependencies=[HumanDep]`, it refuses before the route's body runs: before
    the rate limit bookkeeping and any database or mail work. The token is read from the
    header directly, not declared as a parameter, so the OpenAPI schema and the generated web
    client stay as they are. Passes everything while Turnstile is off.
    """
    if not settings.turnstile_enabled:
        return
    verified = await turnstile_service.verify(
        settings,
        request.headers.get(turnstile_service.TOKEN_HEADER),
        remote_ip=request.client.host if request.client else None,
    )
    if not verified:
        raise AppError(
            ErrorCode.turnstile_failed,
            messages_for(settings=settings).turnstile_failed,
            status_code=403,
        )


HumanDep = Depends(require_human)


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


async def optional_user_ungated(request: Request, db: DbDep, settings: SettingsDep) -> User | None:
    """
    Return the signed-in user, or None for a guest, whatever they have accepted.

    Signed in means: the session cookie hashes to an unexpired session of an
    account that is active and not deleted. Knowing a user's id grants nothing;
    a route that needs an owner checks the owner against this user.

    Only the routes that must work before the terms are accepted use this one
    (`tests/test_legal_gate.py` lists them): everything else goes through
    `OptionalUser` or `CurrentUser`, which also check the acceptance.
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


UngatedOptionalUser = Annotated[User | None, Depends(optional_user_ungated)]


async def current_user_ungated(user: UngatedOptionalUser) -> User:
    """Return the signed-in user, or answer 401, whatever they have accepted."""
    if user is None:
        raise AppError(ErrorCode.UNAUTHORIZED, "Sign in first.", status_code=401)
    return user


UngatedCurrentUser = Annotated[User, Depends(current_user_ungated)]


async def optional_user(user: UngatedOptionalUser, db: DbDep, settings: SettingsDep) -> User | None:
    """
    Return the signed-in user, or None for a guest; 403 while the user has to accept again.

    The acceptance of the terms and the privacy policy is enforced here, on the server
    (decision 35): a signed-in account whose acceptance is missing or out of date gets
    `legal_acceptance_required` from every route that takes this dependency.
    """
    if user is not None and await legal_service.acceptance_required(db, settings, user.id):
        raise legal_service.acceptance_error(settings, 403)
    return user


OptionalUser = Annotated[User | None, Depends(optional_user)]


async def current_user(user: OptionalUser) -> User:
    """Return the signed-in user, or answer 401; 403 while they have to accept again."""
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


async def public_member(user: VerifiedUser) -> User:
    """
    Return a verified user who has chosen a public handle.

    Everything that puts a person on something other people read (a post, a comment, a
    follow) depends on this: only the handle chosen for the network is ever shown, and the
    real full name beside it only with its own consent (`public_identity.shown_name`).
    """
    if user.handle is None:
        raise AppError(
            ErrorCode.PUBLIC_IDENTITY_REQUIRED,
            "Choose a public handle first.",
            status_code=409,
        )
    return user


PublicMember = Annotated[User, Depends(public_member)]


def requires(
    *flags: FeatureFlag, code: ErrorCode = ErrorCode.NOT_FOUND
) -> Callable[[SettingsDep], None]:
    """
    Return a dependency that answers 404 while none of `flags` is on.

    A feature that is off is absent, not hidden: the answer is the one an unregistered path
    gets. Settings are read at call time, so a test (or a reload) that changes them is heard.
    """

    def check(settings: SettingsDep) -> None:
        if not any(settings.is_enabled(flag) for flag in flags):
            raise AppError(code, "Not found.", status_code=404)

    return check


# The network alone opens posts, feeds and follows. The public identity and the reports serve
# the atlas too: it publishes under the handle, and a place on the map is reported through the
# same route as a post. Comments have their own switch (decision 63).
require_social = requires(FeatureFlag.SOCIAL)
require_social_or_atlas = requires(FeatureFlag.SOCIAL, FeatureFlag.ATLAS)
require_comments = requires(FeatureFlag.SOCIAL_COMMENTS)


def get_insight_source(request: Request) -> InsightSource:
    """
    Return where publishable insights are read from.

    The insights feature sets `app.state.insight_source` when it builds the application
    (see `create_app`); until it does, publishing answers 503 rather than inventing
    an insight.
    """
    source: InsightSource | None = getattr(request.app.state, "insight_source", None)
    if source is None:
        raise AppError(
            ErrorCode.SERVICE_UNAVAILABLE,
            "Publishing insights is not available yet.",
            status_code=503,
        )
    return source


InsightSourceDep = Annotated[InsightSource, Depends(get_insight_source)]


def get_photo_store(request: Request, settings: SettingsDep) -> PhotoStore:
    """
    Return the photo store the settings describe, built once per application.

    A test sets `app.state.photo_store` to one on a temporary directory; otherwise the store
    is built from the settings (the S3 bucket, or the local disk in development, decision 44).
    """
    store: PhotoStore | None = getattr(request.app.state, "photo_store", None)
    if store is None:
        store = build_photo_store(settings)
        request.app.state.photo_store = store
    return store


PhotoStoreDep = Annotated[PhotoStore, Depends(get_photo_store)]


def get_text_guard(request: Request, settings: SettingsDep) -> TextGuard:
    """
    Return the guard every post and comment passes first.

    The OpenAI guard unless `app.state.text_guard` holds another (tests, or a later swap of
    provider); with no key it cannot judge anything, and so holds everything for a person.
    """
    guard: TextGuard | None = getattr(request.app.state, "text_guard", None)
    return guard if guard is not None else OpenAiTextGuard(settings)


TextGuardDep = Annotated[TextGuard, Depends(get_text_guard)]


def limited(kind: WriteKind) -> Any:
    """Build the dependency that counts one write of `kind` against the caller's own budget."""

    def enforce(request: Request, user: CurrentUser) -> None:
        retry_after = get_social_limits(request).hit(kind, str(user.id))
        if retry_after is not None:
            raise too_many_requests(retry_after, "Too many actions. Try again later.")

    return Depends(enforce)
