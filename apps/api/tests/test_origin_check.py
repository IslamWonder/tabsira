from __future__ import annotations

import pytest

from src.main import create_app
from tests.helpers import client_for


@pytest.fixture
async def browser(make_settings):
    """An application with a route per method, and a client that sends what the test says."""
    settings = make_settings(
        cors_origins="https://tabsira.test,https://www.tabsira.test",
        api_url="https://api.tabsira.test",
    )
    application = create_app(settings)

    @application.api_route(
        "/_probe", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    )
    async def probe() -> dict[str, bool]:
        return {"reached": True}

    async with client_for(application) as client:
        yield client


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize(
    "origin",
    [
        "https://tabsira.test",
        "https://www.tabsira.test",
        "https://api.tabsira.test",
        "HTTPS://TABSIRA.TEST",
    ],
)
async def test_an_allowed_origin_may_change_state(browser, method, origin):
    response = await browser.request(method, "/_probe", headers={"Origin": origin})

    assert response.status_code == 200


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example",
        "null",
        "http://tabsira.test",
        "https://tabsira.test.evil.example",
        "https://sibling.tabsira.test",
        "",
    ],
)
async def test_any_other_origin_is_refused_with_a_json_403(browser, method, origin):
    response = await browser.request(method, "/_probe", headers={"Origin": origin})

    assert response.status_code == 403
    assert response.json() == {
        "error": "ORIGIN_NOT_ALLOWED",
        "detail": "This request does not come from an allowed origin.",
    }
    assert len(response.headers["x-request-id"]) == 32


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
async def test_reads_are_never_checked(browser, method):
    response = await browser.request(method, "/_probe", headers={"Origin": "https://evil.example"})

    assert response.status_code != 403


async def test_a_browser_that_sends_no_origin_is_judged_by_sec_fetch_site(browser):
    for site, allowed in (
        ("same-origin", True),
        ("none", True),
        ("same-site", False),
        ("cross-site", False),
    ):
        response = await browser.post("/_probe", headers={"Sec-Fetch-Site": site})

        assert (response.status_code == 200) is allowed, site


async def test_the_origin_decides_when_both_headers_are_there(browser):
    allowed = await browser.post(
        "/_probe", headers={"Origin": "https://tabsira.test", "Sec-Fetch-Site": "cross-site"}
    )
    refused = await browser.post(
        "/_probe", headers={"Origin": "https://evil.example", "Sec-Fetch-Site": "same-origin"}
    )

    assert (allowed.status_code, refused.status_code) == (200, 403)


async def test_a_caller_that_is_not_a_browser_sends_neither_header_and_passes(browser):
    assert (await browser.post("/_probe")).status_code == 200


async def test_the_refusal_still_carries_the_cors_headers_for_an_allowed_cors_origin_only(browser):
    refused = await browser.post("/_probe", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in refused.headers


async def test_websocket_and_lifespan_scopes_pass_through(make_settings):
    from src.middleware.origin_check import OriginCheckMiddleware

    seen = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    middleware = OriginCheckMiddleware(app, ["https://tabsira.test"])

    await middleware({"type": "lifespan"}, None, None)
    await middleware({"type": "websocket", "method": "POST", "headers": []}, None, None)

    assert seen == ["lifespan", "websocket"]
