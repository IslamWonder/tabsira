"""Who is calling: the session lookup, and the verified-address gate for anything public."""

from __future__ import annotations

import pytest

from src.deps import CurrentUser, OptionalUser, VerifiedUser
from tests.conftest import PASSPHRASE

LOGIN = {"email": "reader@example.com", "password": PASSPHRASE}


@pytest.fixture
def probes(account_app):
    @account_app.get("/_who")
    async def who(user: OptionalUser) -> dict[str, str | None]:
        return {"email": user.email if user else None}

    @account_app.get("/_current")
    async def current(user: CurrentUser) -> dict[str, str]:
        return {"email": user.email}

    @account_app.post("/_publish")
    async def publish(user: VerifiedUser) -> dict[str, str]:
        return {"email": user.email}

    return account_app


async def test_a_guest_is_none_and_has_no_access_to_a_current_user_route(web, probes):
    assert (await web.get("/_who")).json() == {"email": None}
    assert (await web.get("/_current")).status_code == 401


async def test_a_session_makes_the_caller_the_user(web, probes, make_user):
    await make_user()
    await web.post("/auth/login", json=LOGIN)

    assert (await web.get("/_who")).json() == {"email": "reader@example.com"}
    assert (await web.get("/_current")).json() == {"email": "reader@example.com"}


async def test_a_cookie_that_names_no_session_is_a_guest(web, probes):
    web.cookies.set("__Secure-tabsira_session", "not-a-session", domain=".tabsira.test")

    assert (await web.get("/_who")).json() == {"email": None}


async def test_an_unverified_address_cannot_publish(web, probes, make_user):
    await make_user(verified=False)
    await web.post("/auth/login", json=LOGIN)

    response = await web.post("/_publish")

    assert response.status_code == 403
    assert response.json() == {
        "error": "EMAIL_NOT_VERIFIED",
        "detail": "Verify your e-mail address first.",
    }


async def test_a_verified_address_can_publish(web, probes, make_user):
    await make_user(verified=True)
    await web.post("/auth/login", json=LOGIN)

    assert (await web.post("/_publish")).status_code == 200


async def test_a_guest_cannot_publish_either(web, probes):
    assert (await web.post("/_publish")).status_code == 401


async def test_the_ip_hash_dependency_copes_with_a_request_that_has_no_client(account_settings):
    from starlette.requests import Request

    from src import deps

    request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "client": None})

    assert deps.get_ip_hash(request, account_settings) == deps.get_ip_hash(
        request, account_settings
    )
    assert len(deps.get_ip_hash(request, account_settings)) == 64


async def test_the_google_client_is_built_once_per_process(account_app, account_settings):
    from starlette.requests import Request

    from src import deps

    request = Request(
        {"type": "http", "method": "GET", "path": "/", "headers": [], "app": account_app}
    )
    account_app.state.google_oidc = None

    first = deps.get_google_oidc(request, account_settings)

    assert deps.get_google_oidc(request, account_settings) is first
