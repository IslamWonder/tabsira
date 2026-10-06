"""The two Google routes, with Google replaced by tests/google_fake.py: no network."""

from __future__ import annotations

import logging
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import func, select

from src.models import OAuthAccount, OAuthState, Session, User
from src.services import auth_service, google_oidc
from src.services.google_oidc import GoogleOidc
from tests.conftest import PASSPHRASE, browser_for
from tests.google_fake import Google, sign

SESSION_COOKIE = "__Secure-tabsira_session"
BINDER_COOKIE = "__Secure-tabsira_oauth"


@pytest.fixture
def google(account_app, account_settings):
    fake = Google()
    account_app.state.google_oidc = GoogleOidc(
        account_settings, transport=httpx.MockTransport(fake.handler)
    )
    return fake


async def begin(web, next_path=None):
    """Start a sign-in the way the browser does; return (state, nonce, challenge)."""
    params = {"next": next_path} if next_path else {}
    response = await web.get("/auth/google/start", params=params)
    assert response.status_code == 302, response.text
    query = {k: v[0] for k, v in parse_qs(urlsplit(response.headers["location"]).query).items()}
    return query["state"], query["nonce"], query["code_challenge"]


async def finish(web, google, state, nonce, **claims):
    google.token_response = httpx.Response(
        200, json={"id_token": sign(google.key, nonce=nonce, **claims)}
    )
    return await web.get("/auth/google/callback", params={"code": "the-code", "state": state})


def lands_on(response, path):
    return (
        response.status_code == 302
        and response.headers["location"] == f"https://tabsira.test{path}"
    )


# ─── Not configured ───────────────────────────────────────────────────────────


async def test_both_routes_answer_503_when_google_is_not_configured(make_settings, db_session):
    from src.database import get_db
    from src.main import create_app

    application = create_app(make_settings())

    async def use_session():
        yield db_session

    application.dependency_overrides[get_db] = use_session
    async with browser_for(application) as client:
        start = await client.get("/auth/google/start")
        callback = await client.get("/auth/google/callback", params={"code": "c", "state": "s"})

    for response in (start, callback):
        assert response.status_code == 503
        assert response.json() == {
            "error": "GOOGLE_NOT_CONFIGURED",
            "detail": "Google sign-in is not configured.",
        }


# ─── Start ────────────────────────────────────────────────────────────────────


async def test_start_redirects_to_google_with_pkce_state_and_nonce(web, db_session, google):
    response = await web.get("/auth/google/start")

    location = urlsplit(response.headers["location"])
    query = {k: v[0] for k, v in parse_qs(location.query).items()}
    assert response.status_code == 302
    assert (
        f"{location.scheme}://{location.netloc}{location.path}"
        == google_oidc.AUTHORIZATION_ENDPOINT
    )
    assert query["response_type"] == "code"
    assert query["code_challenge_method"] == "S256"
    assert query["redirect_uri"] == "https://api.tabsira.test/auth/google/callback"
    assert query["scope"] == "openid email profile"
    row = await db_session.scalar(select(OAuthState))
    # The verifier never leaves the server; only its challenge is in the URL.
    assert google_oidc.pkce_challenge(row.code_verifier) == query["code_challenge"]
    assert row.code_verifier not in response.headers["location"]
    assert row.nonce == query["nonce"]
    assert response.headers["cache-control"] == "no-store"


async def test_start_ties_the_flow_to_the_browser_with_a_cookie_on_the_google_routes_only(
    web, google
):
    response = await web.get("/auth/google/start")

    cookie = response.headers["set-cookie"]
    parts = {part.strip() for part in cookie.split(";")}
    assert cookie.startswith(f"{BINDER_COOKIE}=")
    assert {"HttpOnly", "Secure", "SameSite=lax", "Path=/auth/google", "Max-Age=600"} <= parts
    assert not any(part.startswith("Domain") for part in parts)


async def test_start_keeps_a_next_path_and_drops_an_address_elsewhere(web, db_session, google):
    await begin(web, "/world")
    await begin(web, "https://evil.example/steal")

    paths = sorted(
        (await db_session.scalars(select(OAuthState.next_path))).all(), key=lambda p: p or ""
    )
    assert paths == [None, "/world"]


async def test_start_is_rate_limited_per_ip(web, google):
    statuses = [(await web.get("/auth/google/start")).status_code for _ in range(22)]

    assert statuses == [302] * 20 + [429, 429]


# ─── Callback: success ────────────────────────────────────────────────────────


async def test_a_new_person_gets_an_account_a_session_and_lands_on_the_web_app(
    web, db_session, google
):
    state, nonce, challenge = await begin(web, "/world")

    response = await finish(web, google, state, nonce)

    assert lands_on(response, "/world")
    (sent,) = google.token_calls
    assert google_oidc.pkce_challenge(sent["code_verifier"][0]) == challenge
    assert sent["code"] == ["the-code"]
    me = (await web.get("/auth/me")).json()
    assert (me["email"], me["display_name"]) == ("reader@example.com", "Reader")
    assert (me["email_verified"], me["has_password"], me["providers"]) == (True, False, ["google"])
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith(SESSION_COOKIE))
    assert {"HttpOnly", "Secure", "SameSite=lax", "Domain=.tabsira.test"} <= {
        part.strip() for part in session_cookie.split(";")
    }
    assert any(c.startswith(f"{BINDER_COOKIE}=") and "Max-Age=0" in c for c in cookies)
    # A new account must accept the texts before it can use anything else.
    assert (await web.get("/profile")).status_code == 403
    await web.post(
        "/auth/legal/accept",
        json={"terms_version": "2026-10-05T18:00Z", "privacy_version": "2026-10-06T00:00Z"},
    )
    assert (await web.get("/profile")).json()["age_range"] == "unknown"
    assert response.headers["cache-control"] == "no-store"


async def test_without_a_next_path_it_lands_on_the_home_page(web, google):
    state, nonce, _ = await begin(web)

    assert lands_on(await finish(web, google, state, nonce), "/")


async def test_the_same_person_signing_in_again_reuses_the_account(web, db_session, google):
    for _ in range(2):
        state, nonce, _ = await begin(web)
        assert lands_on(await finish(web, google, state, nonce), "/")

    assert await db_session.scalar(select(func.count()).select_from(User)) == 1
    assert await db_session.scalar(select(func.count()).select_from(OAuthAccount)) == 1
    assert await db_session.scalar(select(func.count()).select_from(Session)) == 1


async def test_a_google_name_is_cut_to_60_characters_and_a_missing_one_stays_empty(
    web, db_session, google
):
    state, nonce, _ = await begin(web)
    await finish(web, google, state, nonce, name="ن" * 100)
    state, nonce, _ = await begin(web)
    await finish(
        web, google, state, nonce, sub="another-sub", email="second.person@example.com", name=None
    )

    names = {u.email: u.display_name for u in (await db_session.scalars(select(User))).all()}
    assert names == {"reader@example.com": "ن" * 60, "second.person@example.com": ""}


async def test_linking_a_verified_password_account_keeps_its_password_and_sessions(
    web, db_session, google, make_user
):
    await make_user(verified=True)
    await web.post("/auth/login", json={"email": "reader@example.com", "password": PASSPHRASE})
    old = web.cookies[SESSION_COOKIE]
    state, nonce, _ = await begin(web)

    await finish(web, google, state, nonce)

    me = (await web.get("/auth/me")).json()
    assert (me["has_password"], me["providers"]) == (True, ["google"])
    assert web.cookies[SESSION_COOKIE] != old


async def test_linking_an_unverified_password_account_removes_the_password_and_ends_its_sessions(
    web, db_session, google, make_user, account_app
):
    # Someone registered the owner's address first and is waiting for them to arrive.
    await make_user(verified=False)
    async with browser_for(account_app) as attacker:
        await attacker.post(
            "/auth/login", json={"email": "reader@example.com", "password": PASSPHRASE}
        )
        state, nonce, _ = await begin(web)

        await finish(web, google, state, nonce)

        assert (await attacker.get("/auth/me")).status_code == 401
    me = (await web.get("/auth/me")).json()
    assert (me["has_password"], me["email_verified"], me["providers"]) == (False, True, ["google"])
    refused = await web.post(
        "/auth/login", json={"email": "reader@example.com", "password": PASSPHRASE}
    )
    assert refused.status_code == 401


async def test_linking_an_unverified_password_account_ends_its_admin_sessions_too(
    web, db_session, google, make_user
):
    from src.services import admin_session_service

    user = await make_user(verified=False, is_admin=True)
    admin_token = await admin_session_service.create(
        db_session, user_id=user.id, ip_hash="ip", user_agent=None
    )
    state, nonce, _ = await begin(web)

    await finish(web, google, state, nonce)

    assert await admin_session_service.find(db_session, admin_token) is None


async def test_a_google_only_account_that_was_never_verified_just_becomes_verified(
    web, google, make_user
):
    await make_user(password=None, verified=False)
    state, nonce, _ = await begin(web)

    await finish(web, google, state, nonce)

    assert (await web.get("/auth/me")).json()["email_verified"] is True


async def test_signing_in_replaces_the_session_the_browser_held(web, google, make_user, db_session):
    await make_user("other@example.com", verified=True)
    await web.post("/auth/login", json={"email": "other@example.com", "password": PASSPHRASE})
    state, nonce, _ = await begin(web)

    await finish(web, google, state, nonce)

    assert (await web.get("/auth/me")).json()["email"] == "reader@example.com"
    assert await db_session.scalar(select(func.count()).select_from(Session)) == 1


# ─── Callback: refusals, all as redirects to the login page ──────────────────


def fails_with(response, code):
    return (
        response.status_code == 302
        and response.headers["location"] == f"https://tabsira.test/signin?error={code}"
    )


async def test_declining_at_google_is_google_denied(web, google):
    state, _, _ = await begin(web)

    response = await web.get(
        "/auth/google/callback", params={"error": "access_denied", "state": state}
    )

    assert fails_with(response, "google_denied")
    assert SESSION_COOKIE not in web.cookies


async def test_any_other_google_error_or_a_missing_code_is_google_failed(web, google):
    state, _, _ = await begin(web)
    other = await web.get("/auth/google/callback", params={"error": "server_error", "state": state})
    state, _, _ = await begin(web)
    no_code = await web.get("/auth/google/callback", params={"state": state})

    assert fails_with(other, "google_failed")
    assert fails_with(no_code, "google_failed")


async def test_a_callback_without_a_state_or_with_an_unknown_one_is_google_state(web, google):
    assert fails_with(await web.get("/auth/google/callback", params={"code": "c"}), "google_state")
    assert fails_with(
        await web.get("/auth/google/callback", params={"code": "c", "state": "never-issued"}),
        "google_state",
    )


async def test_a_state_works_once(web, google):
    state, nonce, _ = await begin(web)
    assert lands_on(await finish(web, google, state, nonce), "/")

    assert fails_with(await finish(web, google, state, nonce), "google_state")


async def test_a_callback_from_a_browser_that_did_not_start_the_sign_in_is_refused(
    web, google, account_app, db_session
):
    # The attacker starts a sign-in and hands the victim the callback link.
    state, nonce, _ = await begin(web)
    async with browser_for(account_app) as victim:
        response = await finish(victim, google, state, nonce)

        assert fails_with(response, "google_state")
        assert (await victim.get("/auth/me")).status_code == 401
    assert await db_session.scalar(select(func.count()).select_from(User)) == 0
    assert google.token_calls == []


async def test_an_expired_sign_in_is_refused(web, google, moving_clock):
    state, nonce, _ = await begin(web)
    moving_clock.advance(seconds=601)

    assert fails_with(await finish(web, google, state, nonce), "google_state")


async def test_a_refused_exchange_or_id_token_is_google_failed_and_logs_no_secret(
    web, google, caplog
):
    state, _, _ = await begin(web)
    google.token_response = httpx.Response(400, json={"error": "invalid_grant"})
    with caplog.at_level(logging.WARNING, logger="tabsira.google"):
        refused_code = await web.get(
            "/auth/google/callback", params={"code": "secret-code", "state": state}
        )

    state, _, _ = await begin(web)
    with caplog.at_level(logging.WARNING, logger="tabsira.google"):
        wrong_nonce = await finish(web, google, state, "someone-elses-nonce")

    assert fails_with(refused_code, "google_failed")
    assert fails_with(wrong_nonce, "google_failed")
    assert "Google sign-in refused: token endpoint answered 400" in caplog.text
    assert "secret-code" not in caplog.text
    assert "id_token" not in caplog.text


async def test_an_unverified_google_address_is_refused(web, google, db_session):
    state, nonce, _ = await begin(web)

    response = await finish(web, google, state, nonce, email_verified=False)

    assert fails_with(response, "google_failed")
    assert await db_session.scalar(select(func.count()).select_from(User)) == 0


async def test_a_disabled_account_is_not_signed_in_and_nothing_is_linked_to_it(
    web, google, make_user, db_session
):
    await make_user(is_active=False, verified=True)
    state, nonce, _ = await begin(web)

    response = await finish(web, google, state, nonce)

    assert fails_with(response, "account_disabled")
    assert await db_session.scalar(select(func.count()).select_from(OAuthAccount)) == 0
    assert SESSION_COOKIE not in web.cookies


async def test_an_already_linked_account_that_was_disabled_since_is_refused(
    web, google, db_session
):
    state, nonce, _ = await begin(web)
    await finish(web, google, state, nonce)
    await web.post("/auth/logout")
    user = await db_session.scalar(select(User))
    user.is_active = False
    await db_session.flush()
    state, nonce, _ = await begin(web)

    assert fails_with(await finish(web, google, state, nonce), "account_disabled")


async def test_two_callbacks_racing_for_one_new_person_leave_one_link_and_one_error(
    web, google, db_session, make_user, monkeypatch
):
    other = await make_user("elsewhere@example.com", verified=True)
    real_find = auth_service.find_by_email

    async def another_callback_wins_first(db, email):
        db.add(OAuthAccount(user_id=other.id, provider="google", subject="1234567890"))
        await db.flush()
        return await real_find(db, email)

    # The lookup of the linked identity already missed; the other request links it now.
    monkeypatch.setattr(auth_service, "find_by_email", another_callback_wins_first)
    state, nonce, _ = await begin(web)

    response = await finish(web, google, state, nonce)

    assert fails_with(response, "google_failed")
    assert await db_session.scalar(select(func.count()).select_from(OAuthAccount)) == 1
    assert SESSION_COOKIE not in web.cookies
