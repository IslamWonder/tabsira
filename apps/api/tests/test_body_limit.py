"""The body cap: a declared length is refused at once, an undeclared one is cut off."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from src.middleware.body_limit import BodyLimitMiddleware


class Echo:
    """An ASGI app that reads the whole body and says how long it was."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        self.calls += 1
        body = b""
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": str(len(body)).encode()})


def scope_for(path: str, headers: list[tuple[bytes, bytes]]) -> dict[str, Any]:
    return {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": headers,
        "query_string": b"",
        "state": {},
    }


async def run(app: Any, scope: dict[str, Any], chunks: list[bytes]) -> tuple[int, bytes]:
    queue = [
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ]
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, body


@pytest.fixture
def echo() -> Echo:
    return Echo()


@pytest.fixture
def limited(echo: Echo) -> BodyLimitMiddleware:
    return BodyLimitMiddleware(echo, limits={"/small": 10})


async def test_a_body_within_the_limit_passes_untouched(limited, echo):
    scope = scope_for("/small", [(b"content-length", b"10")])

    assert await run(limited, scope, [b"12345", b"67890"]) == (200, b"10")


async def test_a_declared_length_over_the_limit_is_refused_before_the_app_runs(limited, echo):
    scope = scope_for("/small", [(b"content-length", b"11")])

    status, body = await run(limited, scope, [b"12345678901"])

    assert status == 413
    assert b'"PAYLOAD_TOO_LARGE"' in body
    assert echo.calls == 0


async def test_a_body_with_no_declared_length_is_cut_off_at_the_limit(limited):
    scope = scope_for("/small", [])

    # Three chunks of six bytes: the app sees ten and no more.
    assert await run(limited, scope, [b"abcdef", b"ghijkl", b"mnopqr"]) == (200, b"10")
    # A single chunk that is too long is shortened.
    assert await run(limited, scope, [b"x" * 500]) == (200, b"10")


async def test_a_length_that_is_not_a_number_falls_back_to_the_cut(limited):
    scope = scope_for("/small", [(b"content-length", b"lots")])

    assert await run(limited, scope, [b"x" * 40]) == (200, b"10")


async def test_other_paths_and_other_scopes_are_not_limited(limited, echo):
    assert await run(limited, scope_for("/other", []), [b"x" * 500]) == (200, b"500")

    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "lifespan.startup"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await limited({"type": "lifespan"}, receive, send)
    assert echo.calls == 2


async def test_a_message_that_is_not_a_body_chunk_goes_through():
    seen: list[dict[str, Any]] = []

    async def downstream(scope: Any, receive: Any, send: Any) -> None:
        seen.append(await receive())

    async def receive() -> dict[str, Any]:
        return {"type": "http.disconnect"}

    async def send(_message: dict[str, Any]) -> None:
        return None

    app = BodyLimitMiddleware(downstream, limits={"/small": 10})
    await app(scope_for("/small", []), receive, send)

    assert seen == [{"type": "http.disconnect"}]


async def test_the_real_client_is_refused_with_the_standard_error_body(limited):
    async with AsyncClient(transport=ASGITransport(app=limited), base_url="http://t") as http:
        response = await http.post("/small", content=b"x" * 11)

    assert response.status_code == 413
    assert response.json()["error"] == "PAYLOAD_TOO_LARGE"
