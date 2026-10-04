"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from src.admin import install_admin
from src.config import Settings, get_settings
from src.database import dispose_engine
from src.error_tracking import WebReporter, init_error_tracking, shutdown_error_tracking
from src.errors import ErrorResponse, register_error_handlers
from src.middleware.admin_scope import AdminHostMiddleware, NoCorsForAdminMiddleware
from src.middleware.body_limit import BodyLimitMiddleware
from src.middleware.no_store import NoStoreMiddleware
from src.middleware.origin_check import OriginCheckMiddleware
from src.middleware.request_id import REQUEST_ID_HEADER, RequestIdMiddleware
from src.redis_client import close_redis
from src.responses import OrjsonResponse
from src.routers import (
    account,
    atlas,
    auth,
    auth_email,
    client_errors,
    comments,
    cookie_consent,
    feed,
    geo,
    google_auth,
    health,
    insights,
    legal,
    me,
    media,
    members,
    posts,
    profile,
    public_insights,
    reactions,
    reports,
    scans,
    scripture,
    sitemap,
    sounds,
    support,
    tutorial,
    world,
)
from src.scans.queue import close_queue
from src.services import (  # noqa: F401 - the sitemaps register themselves
    atlas_sitemap,
    social_sitemap,
    turnstile_service,
)
from src.services.insight_source import InsightSource
from src.services.insight_table_source import InsightTableSource
from src.storage.notice import announce_storage
from src.storage.probe import check_storage

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
    {
        "name": "atlas",
        "description": "«أطلس بصائر العالم»: insights placed on the map at approximate points.",
    },
    {"name": "scripture", "description": "Quran verses and hadith, read-only, exactly as stored."},
    {"name": "sitemap", "description": "The public pages for the web app's sitemaps."},
    {"name": "support", "description": "The support form: an e-mail to the team, nothing stored."},
    {
        "name": "posts",
        "description": "Posts made from verified insights: drafts, submission, withdrawal.",
    },
    {"name": "reactions", "description": "Likes and bookmarks."},
    {"name": "comments", "description": "Comments on a post and replies to them."},
    {"name": "reports", "description": "Reports of posts and comments, with a reason."},
    {"name": "feed", "description": "«أتابع», «لك» and the latest, and a member's posts."},
    {
        "name": "members",
        "description": "The public handle and name, public profiles, follows and blocks.",
    },
    {
        "name": "legal",
        "description": "Versions of the terms and privacy texts, and the contact addresses.",
    },
    {
        "name": "client-errors",
        "description": "Errors the browser saw, forwarded to GlitchTip when it is configured.",
    },
    {
        "name": "scans",
        "description": "A photo in, insights out: the background job and its progress.",
    },
    {
        "name": "insights",
        "description": "An insight with its scripture from the store; chat, small step, «تمّ».",
    },
    {
        "name": "public",
        "description": "What a stranger may read: published insights, nothing private.",
    },
    {"name": "world", "description": "The learner's map under fog, its places and treasures."},
    {"name": "me", "description": "Practice, never piety: ranks, streak, quest, sky, badges."},
    {"name": "tutorial", "description": "The prepared rain scene, «مثال موثّق مُعدّ»."},
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Prove the photo storage works before serving, then release everything on stop.

    On stop it flushes error reports, then releases the database, Redis, queue and HTTP
    connections. In production a storage that cannot be used raises here, so the worker exits at boot
    (decision 44).
    """
    await check_storage(app.state.settings)
    yield
    shutdown_error_tracking()
    reporter: WebReporter | None = getattr(app.state, "web_reporter", None)
    if reporter is not None:
        reporter.flush()
    http = getattr(app.state, "http", None)
    if http is not None:
        await http.aclose()
    await turnstile_service.close_http_client()
    await close_queue()
    await close_redis()
    await dispose_engine()


def document_models(app: FastAPI, models: Sequence[type[BaseModel]]) -> None:
    """
    Add `models` to the OpenAPI components.

    A route that reads its own body (an upload or a JSON address on one path)
    refers to its schema by name; FastAPI only registers the models it validates.
    """
    build = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = build()
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for model in models:
            described = model.model_json_schema(ref_template="#/components/schemas/{model}")
            components.update(described.pop("$defs", {}))
            components[model.__name__] = described
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]


def create_app(
    settings: Settings | None = None, *, insight_source: InsightSource | None = None
) -> FastAPI:
    """
    Build the application; `settings` defaults to the process-wide ones.

    `insight_source` is where the social network reads the insight a post publishes (see
    `services/insight_source.py`): the insights table unless a test hands in a double.
    """
    settings = settings or get_settings()
    # Before the application exists: the SDK hooks the framework as it is assembled.
    init_error_tracking(settings, API_VERSION)
    announce_storage(settings)

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
    app.state.insight_source = (
        insight_source if insight_source is not None else InsightTableSource()
    )
    document_models(app, scans.DOCUMENTED_BODIES)

    register_error_handlers(app)

    # Innermost of them, so a refusal still carries the request id and the CORS headers.
    app.add_middleware(
        BodyLimitMiddleware,
        limits={
            "/client-errors": client_errors.MAX_BODY_BYTES,
            "/consent": cookie_consent.MAX_BODY_BYTES,
            "/support": support.MAX_BODY_BYTES,
            "/scans": scans.upload_body_limit(settings),
        },
    )
    app.add_middleware(
        OriginCheckMiddleware,
        allowed_origins=settings.allowed_origins,
        admin_origin=settings.admin_url,
    )
    app.add_middleware(NoStoreMiddleware)
    app.add_middleware(RequestIdMiddleware)
    # Outermost but for the host gate: a preflight is answered before anything else runs and
    # every response carries the CORS headers, except under /admin, which never does.
    app.add_middleware(
        NoCorsForAdminMiddleware,
        allow_origins=settings.cors_origins,
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
    app.include_router(members.router)
    app.include_router(posts.router)
    app.include_router(reactions.router)
    app.include_router(comments.router)
    app.include_router(reports.router)
    app.include_router(feed.router)
    app.include_router(legal.router)
    app.include_router(support.router)
    app.include_router(scans.router)
    app.include_router(insights.router)
    app.include_router(public_insights.router)
    app.include_router(world.router)
    app.include_router(me.router)
    app.include_router(atlas.router)
    app.include_router(media.router)
    app.include_router(tutorial.router)
    app.include_router(sounds.router)
    # The admin area is not mounted at all while its feature flag is off.
    if settings.feature_admin:
        install_admin(app, settings)
        # Outside everything: a request for /admin on any host but the admin's is a plain 404
        # before any other layer, the admin included, sees it.
        app.add_middleware(AdminHostMiddleware, admin_host=settings.admin_host)
    return app


app = create_app()
