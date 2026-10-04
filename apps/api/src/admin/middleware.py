"""Headers every admin response carries, and the reset of the per-request CSRF token."""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.admin import csrf

# What a page of the admin area may never be: framed by another site, sniffed into a
# different type, sent to another site as a referrer, or kept by a cache. A static file may
# be cached. The referrer policy is same-origin and not no-referrer on purpose: with
# no-referrer a browser sends `Origin: null` on every form post, even to its own origin, and
# the API's origin check refuses that.
SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
}
NO_STORE = "no-store"


class AdminHeadersMiddleware:
    """
    Wrap the admin app: security headers on every response, no-store on every page.

    It also clears the CSRF token held for templates when a request starts and when it
    ends, so a token set for one request is never seen by another that shares its task
    (a test client calls the app in its own task).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_static = scope["path"].startswith(f"{scope.get('root_path', '')}/statics/")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers[name] = value
                if not is_static:
                    headers["Cache-Control"] = NO_STORE
            await send(message)

        marker = csrf.forget_token()
        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            csrf.restore(marker)
