"""
Cap the size of the body of chosen routes before anything parses it.

A route whose callers need no sign-in must not be a way to make a worker read
megabytes. For each path in `limits`:

- A `Content-Length` over the limit is answered at once with 413 `PAYLOAD_TOO_LARGE`.
- Without a length (chunked transfer) the body is cut off after `limit` bytes, so
  at most that much is ever buffered; a cut JSON document does not parse and the
  route answers its usual 422.
"""

from __future__ import annotations

from collections.abc import Mapping

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.errors import ErrorCode, error_response


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, limits: Mapping[str, int]) -> None:
        self.app = app
        self.limits = dict(limits)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        limit = self.limits.get(scope["path"]) if scope["type"] == "http" else None
        if limit is None:
            await self.app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            response = error_response(
                Request(scope),
                413,
                ErrorCode.PAYLOAD_TOO_LARGE,
                f"The request body may not be larger than {limit} bytes.",
            )
            await response(scope, receive, send)
            return

        received = 0

        async def capped_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] != "http.request":
                return message
            body: bytes = message.get("body", b"")
            if received + len(body) > limit:
                kept = body[: limit - received]
                received = limit
                return {"type": "http.request", "body": kept, "more_body": False}
            received += len(body)
            return message

        await self.app(scope, capped_receive, send)
