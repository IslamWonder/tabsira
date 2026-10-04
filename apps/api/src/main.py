"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.admin import install_admin
from src.config import Settings, get_settings
from src.database import dispose_engine
from src.error_tracking import WebReporter, init_error_tracking, shutdown_error_tracking
from src.errors import ErrorResponse, register_error_handlers
from src.middleware.body_limit import BodyLimitMiddleware
from src.middleware.no_store import NoStoreMiddleware
from src.middleware.origin_check import OriginCheckMiddleware
from src.middleware.request_id import REQUEST_ID_HEADER, RequestIdMiddleware
from src.responses import OrjsonResponse
from src.routers import (
    account,
    auth,
    auth_email,
    client_errors,
    cookie_consent,
    geo,
    google_auth,
    health,
    profile,
    scripture,
    sitemap,
)

API_VERSION = "0.1.0"

OPENAPI_TAGS = [
    {"name": "health", "description": "Liveness and readiness probes."},
    {
        "name": "auth",
        "description": "Sign up, sign in, sign out, Google, e-mail verification, password reset.",
    },
    {"name": "profile", "description": "The optional profile and the consent records."},
    {
        "name": "consent",
        "description": "Cookie consent: the policy, the visitor's choice and the proof of it.",
    },
    {"name": "account", "description": "Export and deletion of everything an account owns."},
    {"name": "geo", "description": "Place search, reverse lookup and countries from GeoNames."},
    {"name": "scripture", "description": "Quran verses and hadith, read-only, exactly as stored."},
    {"name": "sitemap", "description": "The public pages for the web app's sitemaps."},
    {
        "name": "client-errors",
        "description": "Errors the browser saw, forwarded to GlitchTip when it is configured.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Let the last error reports out and release the database connections when the process stops."""
    yield
    shutdown_error_tracking()
    reporter: WebReporter | None = getattr(app.state, "web_reporter", None)
    if reporter is not None:
        reporter.flush()
    await dispose_engine()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application; `settings` defaults to the process-wide ones."""
    settings = settings or get_settings()
    # Before the application exists: the SDK hooks the framework as it is assembled.
    init_error_tracking(settings, API_VERSION)

    app = FastAPI(
        title="TABSIRA API",
        version=API_VERSION,
        description="Photo to insight, backed by one Quran verse and one hadith.",
        default_response_class=OrjsonResponse,
        # Every route can fail in the one documented way, so the generated client
        # types the error body once. It also replaces FastAPI's own 422 schema,
        # which is not what this API returns.
        responses={"default": {"model": ErrorResponse, "description": "An error"}},
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
        # The schema is the contract the web client types are generated from, so
        # it is served everywhere. The interactive pages are for development.
        openapi_url="/openapi.json",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
    )
    app.state.settings = settings

    register_error_handlers(app)

    # Innermost of them, so a refusal still carries the request id and the CORS headers.
    app.add_middleware(
        BodyLimitMiddleware,
        limits={
            "/client-errors": client_errors.MAX_BODY_BYTES,
            "/consent": cookie_consent.MAX_BODY_BYTES,
        },
    )
    app.add_middleware(OriginCheckMiddleware, allowed_origins=settings.allowed_origins)
    app.add_middleware(NoStoreMiddleware)
    app.add_middleware(RequestIdMiddleware)
    # Added last, so it is the outermost layer: a preflight is answered before
    # anything else runs, and every response carries the CORS headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(auth_email.router)
    app.include_router(google_auth.router)
    app.include_router(profile.router)
    app.include_router(account.router)
    app.include_router(geo.router)
    app.include_router(scripture.router)
    app.include_router(client_errors.router)
    app.include_router(cookie_consent.router)
    app.include_router(sitemap.router)
    # The admin area is not mounted at all while its feature flag is off.
    if settings.feature_admin:
        install_admin(app, settings)
    return app


app = create_app()
