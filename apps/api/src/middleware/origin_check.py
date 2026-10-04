"""
CSRF defence: a browser may change state only from an origin we allow.

The session cookie is SameSite=Lax, which keeps it off cross-site POSTs, but the
web app and the API are sibling subdomains of one site, and Lax does not stop a
request from another sibling (a compromised or forgotten subdomain). So every
state-changing request (POST, PUT, PATCH, DELETE) is also checked here:

- With an `Origin` header (every browser sends one on these methods): it must
  be one of the allowed origins, which are CORS_ORIGINS and the API's own
  address. `Origin: null` (sandboxed frames, some redirects) is refused.
- Without one but with `Sec-Fetch-Site`: only `same-origin` and `none` pass.
- With neither, the caller is not a browser (curl, a test, a server): there is no
  ambient cookie for a forged request to ride on, and it passes.

The admin area (`/admin`) is stricter: only its own origin (`ADMIN_URL`) may change state there,
not the web app's origins and not the API's, so a script injected into the web app cannot drive it.

The answer is the usual JSON error, 403 ORIGIN_NOT_ALLOWED.
"""

from __future__ import annotations

from collections.abc import Iterable

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from src.errors import ErrorCode, error_response
from src.middleware.admin_scope import is_admin_path

STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
SAFE_FETCH_SITES = frozenset({"same-origin", "none"})


class OriginCheckMiddleware:
    def __init__(self, app: ASGIApp, allowed_origins: Iterable[str], admin_origin: str) -> None:
        self.app = app
        self.allowed = frozenset(origin.lower() for origin in allowed_origins)
        self.admin_allowed = frozenset([admin_origin.lower()])

    def _permits(self, scope: Scope, headers: Headers) -> bool:
        origin = headers.get("origin")
        if origin is not None:
            allowed = self.admin_allowed if is_admin_path(scope) else self.allowed
            return origin.lower() in allowed
        fetch_site = headers.get("sec-fetch-site")
        if fetch_site is not None:
            return fetch_site.lower() in SAFE_FETCH_SITES
        return True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] not in STATE_CHANGING_METHODS
            or self._permits(scope, Headers(scope=scope))
        ):
            await self.app(scope, receive, send)
            return
        response = error_response(
            Request(scope),
            403,
            ErrorCode.ORIGIN_NOT_ALLOWED,
            "This request does not come from an allowed origin.",
        )
        await response(scope, receive, send)
