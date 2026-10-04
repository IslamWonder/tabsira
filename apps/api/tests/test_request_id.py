from __future__ import annotations

import re
from typing import Any

import pytest

from src.middleware.request_id import REQUEST_ID_HEADER, RequestIdMiddleware


async def test_every_response_carries_a_generated_request_id(client):
    first = await client.get("/health")
    second = await client.get("/health")

    assert re.fullmatch(r"[0-9a-f]{32}", first.headers[REQUEST_ID_HEADER])
    assert first.headers[REQUEST_ID_HEADER] != second.headers[REQUEST_ID_HEADER]


async def test_a_plain_caller_supplied_id_is_kept(client):
    response = await client.get("/health", headers={REQUEST_ID_HEADER: "trace-2026.10_04-abc"})

    assert response.headers[REQUEST_ID_HEADER] == "trace-2026.10_04-abc"


@pytest.mark.parametrize(
    "supplied",
    [
        "short",
        "x" * 65,
        "has space in it",
        "line\\nbreak-id",
        "semi;colon-id",
        "<script>alert</script>",
    ],
)
async def test_an_unsafe_caller_supplied_id_is_replaced(client, supplied):
    response = await client.get("/health", headers={REQUEST_ID_HEADER: supplied})

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers[REQUEST_ID_HEADER])


async def test_the_id_is_stored_in_the_request_state():
    seen: dict[str, Any] = {}

    async def downstream(scope, receive, send):
        seen.update(scope["state"])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    sent: list[dict[str, Any]] = []

    async def collect(message):
        sent.append(message)

    scope = {"type": "http", "headers": []}
    await RequestIdMiddleware(downstream)(scope, None, collect)

    assert re.fullmatch(r"[0-9a-f]{32}", seen["request_id"])
    assert (b"x-request-id", seen["request_id"].encode()) in sent[0]["headers"]


async def test_lifespan_and_websocket_scopes_pass_through_untouched():
    calls: list[str] = []

    async def downstream(scope, receive, send):
        calls.append(scope["type"])

    middleware = RequestIdMiddleware(downstream)
    for scope_type in ("lifespan", "websocket"):
        scope = {"type": scope_type}
        await middleware(scope, None, None)
        assert "state" not in scope

    assert calls == ["lifespan", "websocket"]
