"""The admin area is its own host: no CORS, no foreign host, and state changes only from its origin."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient

from src.main import create_app
from tests.helpers import client_for

ADMIN = "https://admin.tabsira.test"
API = "https://api.tabsira.test"
WEB = "https://tabsira.test"


@pytest.fixture
async def application(make_settings: Any) -> Any:
    return create_app(
        make_settings(cors_origins=WEB, api_url=API, admin_url=ADMIN, feature_admin=True)
    )


@pytest.fixture
async def on_admin_host(application: Any) -> AsyncIterator[AsyncClient]:
    async with client_for(application, ADMIN) as http:
        yield http


@pytest.fixture
async def on_api_host(application: Any) -> AsyncIterator[AsyncClient]:
    async with client_for(application, API) as http:
        yield http


async def test_the_admin_answers_on_its_own_host(on_admin_host):
    response = await on_admin_host.get("/admin/login")

    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/admin", "/admin/", "/admin/login", "/admin/user/list"])
async def test_the_api_host_gets_a_plain_404_for_the_admin_before_any_admin_code_runs(
    on_api_host, path
):
    response = await on_api_host.get(path)

    assert response.status_code == 404
    assert response.text == "Not Found"
    assert response.headers["content-type"].startswith("text/plain")
    assert "set-cookie" not in response.headers
    assert "x-frame-options" not in response.headers


async def test_the_api_host_does_not_get_a_sign_in_either(on_api_host):
    response = await on_api_host.post("/admin/login", data={"email": "a@b.co"})

    assert response.status_code == 404


async def test_a_host_that_only_looks_like_the_admin_is_refused(application):
    async with client_for(application, "https://admin.tabsira.test.evil.example") as http:
        assert (await http.get("/admin/login")).status_code == 404


async def test_the_rest_of_the_api_is_still_served_on_the_api_host(on_api_host):
    response = await on_api_host.get("/health")

    assert response.status_code == 200


@pytest.mark.parametrize("origin", [WEB, API, "https://evil.example", ADMIN])
async def test_no_admin_response_carries_a_cors_header(on_admin_host, origin):
    page = await on_admin_host.get("/admin/login", headers={"Origin": origin})
    preflight = await on_admin_host.options(
        "/admin/login",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )

    for response in (page, preflight):
        assert not [name for name in response.headers if name.startswith("access-control-")]


async def test_the_rest_of_the_api_still_gets_cors_headers(on_api_host):
    response = await on_api_host.get("/health", headers={"Origin": WEB})

    assert response.headers["access-control-allow-origin"] == WEB
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.parametrize("origin", [WEB, API, "https://evil.example", "null"])
async def test_a_state_change_from_any_origin_but_the_admins_is_refused(on_admin_host, origin):
    response = await on_admin_host.post(
        "/admin/login", data={"email": "a@b.co"}, headers={"Origin": origin}
    )

    assert response.status_code == 403
    assert response.json()["error"] == "ORIGIN_NOT_ALLOWED"
    assert "access-control-allow-origin" not in response.headers


async def test_a_state_change_from_the_admin_origin_reaches_the_admin(on_admin_host):
    response = await on_admin_host.post(
        "/admin/login", data={"email": "a@b.co"}, headers={"Origin": ADMIN}
    )

    # Past the origin check, refused by the sign-in form's own token.
    assert response.status_code == 403
    assert "ORIGIN_NOT_ALLOWED" not in response.text


async def test_the_web_origin_may_still_change_state_elsewhere_in_the_api(on_api_host):
    response = await on_api_host.post("/client-errors", json={}, headers={"Origin": WEB})

    assert response.status_code != 403


async def test_the_admin_cookies_belong_to_the_admin_host_alone(on_admin_host):
    response = await on_admin_host.get("/admin/login")

    cookie = response.headers["set-cookie"].lower()
    assert "domain=" not in cookie
    assert "path=/admin" in cookie
