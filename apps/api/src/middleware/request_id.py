"""Request id middleware."""

from __future__ import annotations

import re
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.error_tracking import tag_request

REQUEST_ID_HEADER = "X-Request-ID"

# A caller may supply its own id so a trace can span services. Only a short,
# plain value is accepted: the id ends up in logs and headers.
_ACCEPTED_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestIdMiddleware:
    """
    Give every HTTP request an id and return it in the `X-Request-ID` header.

    The id is also stored in the request state, where the error handlers and the
    logs read it. Written as a plain ASGI middleware, not on BaseHTTPMiddleware,
    so it adds no extra task per request and cannot break streaming responses.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied = Headers(scope=scope).get(REQUEST_ID_HEADER)
        request_id = supplied if supplied and _ACCEPTED_ID.match(supplied) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        tag_request(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        await self.app(scope, receive, send_with_request_id)
