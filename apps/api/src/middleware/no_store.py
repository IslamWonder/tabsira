"""Keep what belongs to one person out of every cache."""

from __future__ import annotations

from collections.abc import Iterable

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# The routes that answer about one person or set a session or guest cookie:
# accounts, sign-in, the profile, the consents, the export, the social routes,
# whose answers carry the viewer's own likes, saves and follows, and the scan
# workflow (scans, insights, the world, progress, kept tutorial insights). Their responses carry
# `Cache-Control: no-store`, redirects and errors included, which is why this is
# a middleware: a route that returns its own Response would escape a dependency.
PRIVATE_PREFIXES = (
    "/auth",
    "/account",
    "/profile",
    "/consents",
    "/consent",
    # The social network answers with what the viewer liked, saved and follows.
    "/me/",
    "/u/",
    "/blocks",
    "/posts",
    "/feed",
    "/reports",
    "/scans",
    "/insights",
    "/world",
    "/tutorial/rain/insights",
)


class NoStoreMiddleware:
    def __init__(self, app: ASGIApp, prefixes: Iterable[str] = PRIVATE_PREFIXES) -> None:
        self.app = app
        self.prefixes = tuple(prefixes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self.prefixes):
            await self.app(scope, receive, send)
            return

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_with_header)
