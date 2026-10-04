"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import Settings, get_settings
from src.database import dispose_engine
from src.errors import ErrorResponse, register_error_handlers
from src.middleware.no_store import NoStoreMiddleware
from src.middleware.origin_check import OriginCheckMiddleware
from src.middleware.request_id import REQUEST_ID_HEADER, RequestIdMiddleware
from src.responses import OrjsonResponse
from src.routers import account, auth, auth_email, google_auth, health, profile

API_VERSION = "0.1.0"

OPENAPI_TAGS = [
    {"name": "health", "description": "Liveness and readiness probes."},
    {
        "name": "auth",
        "description": "Sign up, sign in, sign out, Google, e-mail verification, password reset.",
    },
    {"name": "profile", "description": "The optional profile and the consent records."},
    {"name": "account", "description": "Export and deletion of everything an account owns."},
]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Release the database connections when the process stops."""
    yield
    await dispose_engine()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application; `settings` defaults to the process-wide ones."""
    settings = settings or get_settings()

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

    # Innermost of the three, so a refusal still carries the request id and the CORS headers.
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
    return app


app = create_app()
