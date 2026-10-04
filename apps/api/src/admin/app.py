"""The admin application: sqladmin, with this product's sign-in, CSRF rules and landing page."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from sqladmin import Admin
from sqladmin.authentication import login_required
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from src.admin import csrf, dashboard
from src.admin.audit import AdminAuditBackend, AuditTrail
from src.admin.auth import AdminAuth
from src.admin.base import current_admin, current_user
from src.admin.middleware import AdminHeadersMiddleware
from src.admin.registry import ViewClass, check_view_policy
from src.config import Settings

BASE_URL = "/admin"
TITLE = "TABSIRA admin"
HERE = Path(__file__).resolve().parent
TEMPLATES_DIR = HERE / "templates"
STATIC_DIR = HERE / "static"
DASHBOARD_TEMPLATE = "admin/dashboard.html"


class TabsiraAdmin(Admin):
    """
    sqladmin's `Admin`, changed in four ways.

    The landing page is the dashboard. Signing in is the product's own form and check
    (`AdminAuth`). Signing out takes a POST, so a link cannot do it. And every action a
    view declares answers POST only, because sqladmin registers them as GET, and a GET
    that changes data is a request any page can forge; the admin script posts them with
    the CSRF token.
    """

    def __init__(
        self,
        app: Starlette,
        *,
        settings: Settings,
        session_maker: async_sessionmaker[AsyncSession],
        auth: AdminAuth,
        trail: AuditTrail,
    ) -> None:
        self.settings = settings
        self.auth = auth
        self.trail = trail
        # The same factory as `session_maker`, typed for the code that is not sqladmin's.
        self.db = session_maker
        super().__init__(
            app=app,
            session_maker=session_maker,
            base_url=BASE_URL,
            title=TITLE,
            templates_dir=str(TEMPLATES_DIR),
            authentication_backend=auth,
            audit_backend=AdminAuditBackend(trail),
            middlewares=[Middleware(AdminHeadersMiddleware)],
            # Looked up before sqladmin's own, so a file here shadows one of the same name.
            static_files_kwargs={"directory": str(STATIC_DIR)},
        )
        auth.templates = self.templates
        self.templates.env.globals["csrf_token"] = csrf.csrf_token
        self._set_methods("logout", ["GET", "POST"])

    def _set_methods(self, name: str, methods: Sequence[str]) -> None:
        """Replace the route called `name` by one that answers `methods`."""
        routes = self.admin.router.routes
        for index, route in enumerate(routes):
            if isinstance(route, Route) and route.name == name:
                routes[index] = Route(
                    route.path,
                    endpoint=route.endpoint,
                    methods=list(methods),
                    name=route.name,
                    include_in_schema=route.include_in_schema,
                )

    def register(self, view: ViewClass) -> None:
        """Add a view after checking it against the admin policy, and make its actions POST."""
        check_view_policy(view)
        self.add_view(view)
        for route in self.admin.router.routes:
            if isinstance(route, Route) and (route.name or "").startswith("action-"):
                self._set_methods(route.name or "", ["POST"])

    async def login(self, request: Request) -> Response:
        if request.method == "GET":
            return await self.auth.render_login(request)
        return await self.auth.login(request)

    async def logout(self, request: Request) -> Response:
        return await self.auth.logout(request)

    @login_required
    async def index(self, request: Request) -> Response:
        """Render the landing page: counts, and a banner when this admin has no second factor."""
        async with self.db() as db:
            stats = await dashboard.collect(db, current_admin(request))
        context = {"title": "Dashboard", "admin_email": current_user(request).email, **stats}
        return await self.templates.TemplateResponse(request, DASHBOARD_TEMPLATE, context)
