"""POST /client-errors: bounded, rate limited, no sign-in, and a 204 whatever happens to the report."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
import sentry_sdk
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.config import Settings
from src.error_tracking import FILTERED, WebReporter
from src.main import create_app
from src.routers import client_errors
from src.routers.client_errors import ClientErrorLimits

WEB_DSN = "https://web-key@glitchtip.example.com/8"
ORIGIN = "https://tabsira.test"
REPORT = {
    "items": [
        {
            "message": "Cannot read properties of undefined",
            "name": "TypeError",
            "stack": "    at render (https://tabsira.me/_next/static/app.js:10:20)",
            "url": "https://tabsira.me/insights/1?token=abc",
            "context": {"route": "/insights", "gender": "man"},
        }
    ]
}


def client_of(application: FastAPI, address: str = "203.0.113.5") -> AsyncClient:
    transport = ASGITransport(app=application, client=(address, 4000), raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="https://api.tabsira.test")


@pytest.fixture
async def open_client(make_settings: Callable[..., Settings]) -> AsyncIterator[AsyncClient]:
    """The application with no GlitchTip configured, as a visitor's browser sees it."""
    async with client_of(create_app(make_settings())) as http:
        yield http


@pytest.fixture
async def forwarding(
    make_settings: Callable[..., Settings], recorder: Any
) -> AsyncIterator[tuple[AsyncClient, FastAPI, Any]]:
    """The application with a web DSN, and what GlitchTip would have received."""
    application = create_app(make_settings(glitchtip_web_dsn=WEB_DSN, glitchtip_release="1.0.0"))
    async with client_of(application) as http:
        yield http, application, recorder


async def test_without_a_dsn_the_answer_is_204_and_nothing_is_built(open_client, monkeypatch):
    def refuse(**_options: Any) -> None:
        raise AssertionError("a client was built without a DSN")

    monkeypatch.setattr(sentry_sdk, "Client", refuse)

    response = await open_client.post("/client-errors", json=REPORT)

    assert response.status_code == 204
    assert response.content == b""


async def test_no_sign_in_is_needed_and_no_cookie_is_read(open_client):
    response = await open_client.post(
        "/client-errors", json=REPORT, headers={"Cookie": "__Secure-tabsira_session=nope"}
    )

    assert response.status_code == 204


async def test_a_report_is_forwarded_cleaned_with_the_request_id_and_browser_family(forwarding):
    http, application, recorder = forwarding

    response = await http.post(
        "/client-errors",
        json=REPORT,
        headers={
            "Origin": ORIGIN,
            "User-Agent": "Mozilla/5.0 (Macintosh) Gecko/20100101 Firefox/132.0",
            "X-Request-ID": "page-load-123456",
        },
    )
    application.state.web_reporter.flush()

    assert response.status_code == 204
    assert response.headers["x-request-id"] == "page-load-123456"
    event = recorder.events[0]
    assert event["platform"] == "javascript"
    assert event["tags"] == {"area": "web", "browser": "firefox", "request_id": "page-load-123456"}
    assert event["request"] == {"url": "https://tabsira.me/insights/1"}
    assert event["extra"]["context"] == {"route": "/insights", "gender": FILTERED}
    assert event["release"] == "tabsira-web@1.0.0"
    assert event["exception"]["values"][0]["type"] == "TypeError"


async def test_the_forwarder_is_built_once_per_application(forwarding):
    http, application, _recorder = forwarding

    await http.post("/client-errors", json=REPORT)
    first = application.state.web_reporter
    await http.post("/client-errors", json=REPORT)

    assert isinstance(first, WebReporter)
    assert application.state.web_reporter is first


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"items": []},
        {"items": [{"message": ""}]},
        {"items": [{"message": "x" * 2001}]},
        {"items": [{"message": "m", "level": "catastrophic"}]},
        {"items": [{"message": "m", "release": "has space"}]},
        {"items": [{"message": "m", "context": {f"k{i}": i for i in range(21)}}]},
        {"items": [{"message": "m", "context": {"nested": {"a": 1}}}]},
        {"items": [{"message": "m"}] * 11},
    ],
)
async def test_a_report_outside_the_schema_is_refused_with_the_standard_body(open_client, body):
    response = await open_client.post("/client-errors", json=body)

    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"


async def test_a_body_over_the_cap_is_refused_before_it_is_read(open_client):
    big = {"items": [{"message": "m", "stack": "x" * 15_000} for _ in range(10)]}
    raw = b" " * (client_errors.MAX_BODY_BYTES + 1)

    response = await open_client.post(
        "/client-errors", content=raw, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert response.json()["error"] == "PAYLOAD_TOO_LARGE"
    # The biggest report the schema allows is well inside the cap.
    assert len(str(big)) < client_errors.MAX_BODY_BYTES
    assert (await open_client.post("/client-errors", json=big)).status_code == 204


async def test_an_address_over_its_budget_gets_429_and_others_are_unaffected(make_settings):
    application = create_app(make_settings())
    limits = ClientErrorLimits()
    limits.per_address.limit = 2
    application.state.client_error_limits = limits

    async with client_of(application, "203.0.113.5") as noisy:
        statuses = [(await noisy.post("/client-errors", json=REPORT)).status_code for _ in range(4)]
        refused = await noisy.post("/client-errors", json=REPORT)
    async with client_of(application, "203.0.113.6") as other:
        fine = await other.post("/client-errors", json=REPORT)

    assert statuses == [204, 204, 429, 429]
    assert refused.json()["error"] == "RATE_LIMITED"
    assert 1 <= int(refused.headers["retry-after"]) <= client_errors.WINDOW_SECONDS
    assert fine.status_code == 204


async def test_every_address_together_is_bounded_too(make_settings):
    application = create_app(make_settings())
    limits = ClientErrorLimits()
    limits.overall.limit = 2
    application.state.client_error_limits = limits

    statuses = []
    for number in range(4):
        async with client_of(application, f"203.0.113.{number + 10}") as http:
            statuses.append((await http.post("/client-errors", json=REPORT)).status_code)

    assert statuses == [204, 204, 429, 429]


async def test_a_page_of_another_origin_is_refused_like_any_state_change(open_client):
    response = await open_client.post(
        "/client-errors", json=REPORT, headers={"Origin": "https://evil.example"}
    )

    assert response.status_code == 403
    assert response.json()["error"] == "ORIGIN_NOT_ALLOWED"


async def test_the_web_app_may_post_across_origins(open_client):
    preflight = await open_client.options(
        "/client-errors",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == ORIGIN


async def test_the_route_is_in_the_published_schema(open_client):
    schema = (await open_client.get("/openapi.json")).json()

    operation = schema["paths"]["/client-errors"]["post"]
    assert operation["tags"] == ["client-errors"]
    assert "204" in operation["responses"]
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ClientReportBatch"
    }
    assert "PAYLOAD_TOO_LARGE" in schema["components"]["schemas"]["ErrorCode"]["enum"]
