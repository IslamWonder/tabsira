"""
Keeps the admin area (`/admin`) apart from the rest of the API.

The admin is served on a host of its own (`ADMIN_URL`), reachable only through the VPN, but
that host and the web app are the same site, so a cookie's `SameSite` rule alone does not keep
a page of the web app away from it. Three rules do:

- `AdminHostMiddleware`: a request for `/admin` whose `Host` is not the admin host (the API's own
  host, say) is a plain 404, before any admin code runs.
- `NoCorsForAdminMiddleware`: the CORS layer is skipped for `/admin`, so no answer from it carries
  `Access-Control-Allow-Origin`, whatever `Origin` the request names, and a page of another
  origin can never read an admin response.
- State-changing requests are checked against the admin origin alone: that is
  `OriginCheckMiddleware`'s `admin_origin`.
"""

from __future__ import annotations

from typing import Any

from starlette.datastructures import Headers
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

ADMIN_PREFIX = "/admin"
NOT_FOUND_BODY = "Not Found"


def is_admin_path(scope: Scope) -> bool:
    """Whether the request is for the admin mount: `/admin` itself or anything under it."""
    path: str = scope.get("path", "")
    return path == ADMIN_PREFIX or path.startswith(f"{ADMIN_PREFIX}/")


class AdminHostMiddleware:
    """Answer 404 for `/admin` on any host but the admin's; a port counts as part of the host."""

    def __init__(self, app: ASGIApp, admin_host: str) -> None:
        self.app = app
        self.admin_host = admin_host.lower()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and is_admin_path(scope)
            and Headers(scope=scope).get("host", "").lower() != self.admin_host
        ):
            await PlainTextResponse(NOT_FOUND_BODY, status_code=404)(scope, receive, send)
            return
        await self.app(scope, receive, send)


class NoCorsForAdminMiddleware:
    """CORS for the whole API except `/admin`, which never gets a CORS header."""

    def __init__(self, app: ASGIApp, **cors_options: Any) -> None:
        self.app = app
        self.cors = CORSMiddleware(app, **cors_options)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and is_admin_path(scope):
            await self.app(scope, receive, send)
        else:
            await self.cors(scope, receive, send)
