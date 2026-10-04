"""
CSRF protection of the admin area: every state-changing request needs the session's token.

The forms and actions are those of the users and sessions views, which are enough to show
the rule: it is enforced in `authenticate`, before any view runs, so it covers every view
registered now or later.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from starlette.requests import Request

from src.admin import csrf
from src.admin.middleware import AdminHeadersMiddleware
from src.models import Session
from tests.support_admin import browser, csrf_of, sign_in, token_of

CSRF_MESSAGE = "The request has no valid CSRF token"


# ─── Forms ─────────────────────────────────────────────────────────


async def test_an_edit_form_carries_the_session_token_in_a_field_and_the_page_in_a_meta_tag(
    admin, make_user
):
    http, _ = admin
    reader = await make_user("reader@example.com")

    page = await http.get(f"/admin/user/edit/{reader.id}")

    token = await csrf_of(http)
    assert page.status_code == 200
    assert f'<input type="hidden" name="csrf_token" value="{token}">' in page.text
    assert f'<meta name="csrf-token" content="{token}">' in page.text
    assert "tabsira-admin.js" in page.text


@pytest.mark.parametrize("data", [{}, {"csrf_token": ""}, {"csrf_token": "forged"}])
async def test_a_form_post_without_the_right_token_is_refused_and_changes_nothing(
    admin, make_user, db_session, data
):
    http, _ = admin
    reader = await make_user("reader@example.com", display_name="Reader")

    response = await http.post(
        f"/admin/user/edit/{reader.id}",
        data={"display_name": "Changed", "is_active": "y", "save": "Save", **data},
    )

    assert response.status_code == 403
    assert CSRF_MESSAGE in response.text
    await db_session.refresh(reader)
    assert reader.display_name == "Reader"


async def test_a_form_post_with_the_token_in_its_field_is_accepted(admin, make_user, db_session):
    http, _ = admin
    reader = await make_user("reader@example.com", display_name="Reader")

    response = await http.post(
        f"/admin/user/edit/{reader.id}",
        data={
            "display_name": "Changed",
            "is_active": "y",
            "save": "Save",
            "csrf_token": await csrf_of(http),
        },
    )

    assert response.status_code == 302
    await db_session.refresh(reader)
    assert reader.display_name == "Changed"


async def test_the_token_may_also_come_in_a_header_as_the_admin_script_sends_it(
    admin, make_user, db_session
):
    http, _ = admin
    reader = await make_user("reader@example.com", display_name="Reader")

    response = await http.post(
        f"/admin/user/edit/{reader.id}",
        headers={"X-CSRF-Token": await csrf_of(http)},
        data={"display_name": "Via header", "is_active": "y", "save": "Save"},
    )

    assert response.status_code == 302
    await db_session.refresh(reader)
    assert reader.display_name == "Via header"


async def test_a_token_of_another_session_does_not_work(admin, make_user, admin_app, make_admin):
    http, _ = admin
    reader = await make_user("reader@example.com")
    await make_admin("second@example.com")
    async with browser(admin_app) as other:
        await sign_in(other, email="second@example.com")
        foreign = await csrf_of(other)

    response = await http.post(
        f"/admin/user/edit/{reader.id}",
        data={"display_name": "X", "is_active": "y", "csrf_token": foreign},
    )

    assert response.status_code == 403


# ─── Actions and deletes ───────────────────────────────────────────


async def test_an_action_is_a_post_never_a_get(admin, db_session, make_user):
    http, _ = admin
    reader = await make_user("reader@example.com", display_name="Reader")
    now = datetime.now(UTC)
    row = Session(
        token_hash=b"\x01" * 32,
        user_id=reader.id,
        expires_at=now + timedelta(days=1),
        last_seen_at=now,
    )
    db_session.add(row)
    await db_session.flush()

    # The address sqladmin links an action to answers GET with "method not allowed".
    assert (await http.get(f"/admin/session/action/revoke?pks={row.id}")).status_code == 405
    assert (await http.post(f"/admin/session/action/revoke?pks={row.id}")).status_code == 403

    response = await http.post(
        f"/admin/session/action/revoke?pks={row.id}", data={"csrf_token": await csrf_of(http)}
    )
    assert response.status_code == 303
    assert (await db_session.scalars(select(Session))).all() == []


async def test_a_delete_needs_the_token_too(admin, make_user):
    http, _ = admin
    reader = await make_user("reader@example.com")

    refused = await http.delete(f"/admin/user/delete?pks={reader.id}")
    allowed = await http.delete(
        f"/admin/user/delete?pks={reader.id}", headers={"X-CSRF-Token": await csrf_of(http)}
    )

    assert refused.status_code == 403
    assert CSRF_MESSAGE in refused.text
    # With the token the request reaches the view, which has no delete at all.
    assert allowed.status_code == 403
    assert CSRF_MESSAGE not in allowed.text


async def test_a_get_never_needs_a_token(admin):
    http, _ = admin

    for path in ("/admin/", "/admin/user/list", "/admin/two-factor"):
        assert (await http.get(path)).status_code == 200


async def test_a_request_without_a_session_gets_the_form_before_the_token_is_looked_at(anon):
    response = await anon.post("/admin/user/edit/anything", data={"display_name": "x"})

    assert response.status_code == 302
    assert response.headers["location"].endswith("/admin/login")


# ─── The script and the headers ────────────────────────────────────


async def test_the_admin_script_is_served_with_the_token_logic_and_may_be_cached(admin):
    http, _ = admin

    script = await http.get("/admin/statics/js/tabsira-admin.js")

    assert script.status_code == 200
    assert "X-CSRF-Token" in script.text
    assert "csrf_token" in script.text
    # The token is posted only to this origin and only under /admin/.
    assert "url.origin === location.origin" in script.text
    assert "url.pathname.startsWith('/admin/')" in script.text
    assert "cache-control" not in script.headers
    assert script.headers["x-content-type-options"] == "nosniff"
    # sqladmin's own assets are still served beside it.
    assert (await http.get("/admin/statics/js/main.js")).status_code == 200


async def test_every_page_is_no_store_and_cannot_be_framed(admin):
    http, _ = admin

    page = await http.get("/admin/user/list")

    assert page.headers["cache-control"] == "no-store"
    assert page.headers["x-frame-options"] == "DENY"
    assert page.headers["referrer-policy"] == "same-origin"


async def test_nothing_the_admin_serves_comes_from_another_host(admin):
    http, _ = admin
    page = (await http.get("/admin/user/list")).text

    hosts = set(re.findall(r'(?:src|href)="(https?://[^/"]+)', page))

    assert hosts <= {"https://admin.tabsira.test"}


# ─── The helpers ───────────────────────────────────────────────────


def test_tokens_match_only_when_both_are_present_and_equal():
    assert csrf.tokens_match("abc", "abc") is True
    assert csrf.tokens_match("abc", "abd") is False
    assert csrf.tokens_match("abc", None) is False
    assert csrf.tokens_match("abc", "") is False
    assert csrf.tokens_match("", "") is False


def test_the_token_templates_see_follows_one_request_and_is_restored(make_settings):
    assert csrf.csrf_token() == ""
    marker = csrf.forget_token()
    csrf.use_token("this-requests-token")
    assert csrf.csrf_token() == "this-requests-token"
    csrf.restore(marker)
    assert csrf.csrf_token() == ""


def test_the_sign_in_token_is_bound_to_the_server_key_and_the_nonce(make_settings):
    one = make_settings(hash_secret="one-secret-of-the-installation-123456")
    two = make_settings(hash_secret="another-secret-of-the-installation-1")

    token = csrf.login_form_token(one, "nonce")

    assert token == csrf.login_form_token(one, "nonce")
    assert token != csrf.login_form_token(one, "other-nonce")
    assert token != csrf.login_form_token(two, "nonce")


@pytest.mark.parametrize("cookie", [None, "", "x" * 200])
def test_a_missing_or_absurd_sign_in_cookie_never_validates(make_settings, cookie):
    settings = make_settings()
    headers = [] if cookie is None else [(b"cookie", f"{csrf.LOGIN_COOKIE_NAME}={cookie}".encode())]
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": headers})

    assert csrf.login_form_valid(settings, request, "anything") is False


async def test_the_headers_middleware_leaves_other_scopes_alone():
    seen = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    await AdminHeadersMiddleware(app)({"type": "lifespan"}, None, None)

    assert seen == ["lifespan"]


async def test_a_page_without_a_token_in_it_is_an_error_for_the_helper(admin):
    http, _ = admin
    plain = await http.get("/admin/statics/css/tabsira-admin.css")

    with pytest.raises(AssertionError, match="no CSRF token"):
        token_of(plain)
