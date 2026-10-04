"""
Signing in to the admin area, and what is checked on every request after that.

Each sign-in outcome is tested through HTTP, as a browser would see it: the form, the
cookie, the redirect, and the row the audit log gets.
"""

from __future__ import annotations

import re

import pyotp
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from src import clock
from src.database import get_db
from src.models import AdminSession, AuditAction
from src.services import admin_totp_service
from tests.support_admin import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    audit_rows,
    browser,
    sign_in,
    token_of,
)

REFUSED = "The e-mail address, the password or the code is wrong."


async def enrol(db_session, settings, admin, moving_clock):
    """Switch the second factor on for `admin`; return its secret and recovery codes."""
    secret = await admin_totp_service.start_enrollment(db_session, settings, admin)
    codes = await admin_totp_service.confirm_enrollment(
        db_session, settings, admin, code_now(secret, moving_clock)
    )
    assert codes is not None
    return secret, codes


def code_now(secret, moving_clock, ahead_steps=0):
    return pyotp.TOTP(secret).at(int(moving_clock.now.timestamp()) + 30 * ahead_steps)


async def session_count(db_session):
    return await db_session.scalar(select(func.count()).select_from(AdminSession))


# ─── The form and a successful sign-in ─────────────────────────────


async def test_the_sign_in_page_is_a_no_store_form_with_its_own_token_and_cookie(anon):
    page = await anon.get("/admin/login")

    assert page.status_code == 200
    for field in ('name="email"', 'name="password"', 'name="code"', 'name="csrf_token"'):
        assert field in page.text
    assert page.headers["cache-control"] == "no-store"
    assert page.headers["x-frame-options"] == "DENY"
    assert page.headers["content-security-policy"] == "frame-ancestors 'none'"
    assert page.headers["referrer-policy"] == "same-origin"
    cookie = page.headers["set-cookie"]
    assert cookie.startswith("__Secure-tabsira_admin_login=")
    for flag in ("HttpOnly", "Secure", "SameSite=strict", "Path=/admin"):
        assert flag in cookie


async def test_a_right_password_opens_a_twelve_hour_strict_session_and_is_audited(
    anon, make_admin, db_session
):
    admin = await make_admin()

    response = await sign_in(anon)

    assert response.status_code == 302
    assert response.headers["location"] == "https://admin.tabsira.test/admin/"
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("__Secure-tabsira_admin="))
    assert "Max-Age=43200" in session_cookie
    for flag in ("HttpOnly", "Secure", "SameSite=strict", "Path=/admin"):
        assert flag in session_cookie
    assert "Domain" not in session_cookie
    # The form's own cookie is dropped once it has been used.
    assert any(c.startswith("__Secure-tabsira_admin_login=") and "Max-Age=0" in c for c in cookies)
    assert (await anon.get("/admin/")).status_code == 200
    row = (await audit_rows(db_session))[0]
    assert (row.action, row.admin_user_id) == (AuditAction.SIGN_IN, admin.id)
    assert re.fullmatch(r"[0-9a-f]{64}", row.ip_hash)
    session = await db_session.scalar(select(AdminSession))
    assert session.user_id == admin.id
    assert session.ip_hash == row.ip_hash


async def test_an_admin_gets_in_with_the_e_mail_in_any_case(anon, make_admin):
    await make_admin("Admin@Example.com")

    assert (await sign_in(anon, email="  ADMIN@example.com ")).status_code == 302


async def test_signing_in_to_the_site_does_not_open_the_admin_area(
    anon, make_admin, admin_app, db_session
):
    async def use_the_test_session():
        yield db_session

    admin_app.dependency_overrides[get_db] = use_the_test_session
    await make_admin()
    async with AsyncClient(
        transport=ASGITransport(app=admin_app, raise_app_exceptions=False),
        base_url="https://api.tabsira.test",
        headers={"Origin": "https://tabsira.test"},
    ) as web:
        login = await web.post(
            "/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login.status_code == 200

        async with browser(admin_app) as admin_host:
            admin_host.cookies.update(web.cookies)
            response = await admin_host.get("/admin/")

    assert response.status_code == 302
    assert response.headers["location"].endswith("/admin/login")


# ─── Refusals: one message, the real reason in the audit log ───────


@pytest.mark.parametrize(
    ("columns", "email", "password", "reason", "known"),
    [
        ({}, ADMIN_EMAIL, "wrong password", "bad_password", True),
        ({}, "nobody@example.com", ADMIN_PASSWORD, "unknown_account", False),
        ({"is_admin": False}, ADMIN_EMAIL, ADMIN_PASSWORD, "not_admin", True),
        ({"is_active": False}, ADMIN_EMAIL, ADMIN_PASSWORD, "account_disabled", True),
        ({"deleted_at": clock.utcnow()}, ADMIN_EMAIL, ADMIN_PASSWORD, "account_disabled", True),
        ({}, "", ADMIN_PASSWORD, "unknown_account", False),
        ({}, ADMIN_EMAIL, "", "bad_password", True),
    ],
    ids=[
        "wrong password",
        "unknown account",
        "not an admin",
        "deactivated",
        "deleted",
        "no e-mail",
        "no password",
    ],
)
async def test_every_refusal_says_the_same_thing_and_the_audit_log_says_why(
    anon, make_admin, db_session, columns, email, password, reason, known
):
    admin = await make_admin(**columns)

    response = await sign_in(anon, email=email, password=password)

    assert response.status_code == 401
    assert REFUSED in response.text
    assert "set-cookie" in response.headers
    assert "__Secure-tabsira_admin=" not in response.headers["set-cookie"]
    assert await session_count(db_session) == 0
    (row,) = await audit_rows(db_session)
    assert row.action is AuditAction.SIGN_IN_FAILED
    assert row.details == {"reason": reason}
    assert row.admin_user_id == (admin.id if known else None)
    # What was typed is never kept.
    assert email not in repr((row.details, row.user_agent, row.ip_hash)) or email == ""


async def test_the_refusal_page_is_the_same_for_a_real_and_an_unknown_account(
    admin_app, make_admin
):
    await make_admin()
    pages = []
    for email in (ADMIN_EMAIL, "nobody@example.com"):
        async with browser(admin_app) as http:
            response = await sign_in(http, email=email, password="wrong")
            pages.append(re.sub(r'value="[^"]*"', 'value=""', response.text))

    assert pages[0].replace(ADMIN_EMAIL, "X") == pages[1].replace("nobody@example.com", "X")


async def test_a_refused_form_keeps_the_address_but_never_the_password(anon, make_admin):
    await make_admin()

    response = await sign_in(anon, password="not the password")

    assert f'value="{ADMIN_EMAIL}"' in response.text
    assert "not the password" not in response.text


# ─── The sign-in form's own CSRF token ─────────────────────────────


async def test_a_sign_in_without_the_forms_token_is_refused_before_any_password_is_checked(
    anon, make_admin, db_session
):
    await make_admin()
    await anon.get("/admin/login")

    response = await anon.post(
        "/admin/login", data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )

    assert response.status_code == 403
    assert "expired" in response.text
    assert await session_count(db_session) == 0
    assert await audit_rows(db_session) == []


async def test_a_token_from_another_form_does_not_match_this_browsers_cookie(admin_app, make_admin):
    await make_admin()
    async with browser(admin_app) as mine, browser(admin_app) as theirs:
        await mine.get("/admin/login")
        stolen = token_of(await theirs.get("/admin/login"))

        response = await mine.post(
            "/admin/login",
            data={
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD,
                "code": "",
                "csrf_token": stolen,
            },
        )

    assert response.status_code == 403


async def test_a_token_without_the_cookie_that_goes_with_it_is_refused(admin_app, make_admin):
    await make_admin()
    async with browser(admin_app) as http:
        token = token_of(await http.get("/admin/login"))
        http.cookies.clear()

        response = await http.post(
            "/admin/login",
            data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "csrf_token": token},
        )

    assert response.status_code == 403


async def test_a_sign_in_from_another_site_is_stopped_by_the_origin_check(anon, make_admin):
    await make_admin()
    page = await anon.get("/admin/login")

    response = await anon.post(
        "/admin/login",
        headers={"Origin": "https://evil.example"},
        data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "csrf_token": token_of(page)},
    )

    assert response.status_code == 403
    assert response.json()["error"] == "ORIGIN_NOT_ALLOWED"


# ─── Rate limiting, with the accounts limiter ──────────────────────


async def test_failed_sign_ins_are_limited_per_address_even_for_the_right_password(
    make_admin_app, make_admin, db_session
):
    await make_admin()
    app = make_admin_app(auth_max_attempts_per_email=2)
    async with browser(app) as http:
        for _ in range(2):
            assert (await sign_in(http, password="wrong")).status_code == 401

        blocked = await sign_in(http)

    assert blocked.status_code == 429
    assert "Too many attempts" in blocked.text
    assert blocked.headers["retry-after"] == "900"
    assert "__Secure-tabsira_admin=" not in blocked.headers["set-cookie"]
    rows = await audit_rows(db_session)
    assert [row.details for row in rows] == [
        {"reason": "bad_password"},
        {"reason": "bad_password"},
        {"reason": "rate_limited"},
    ]
    assert await session_count(db_session) == 0


async def test_the_limit_is_also_per_ip_address_so_other_addresses_do_not_help(
    make_admin_app, make_admin
):
    await make_admin()
    app = make_admin_app(auth_max_attempts_per_ip=3)
    async with browser(app) as http:
        for number in range(3):
            await sign_in(http, email=f"guess{number}@example.com", password="wrong")

        blocked = await sign_in(http, email="another@example.com", password="wrong")

    assert blocked.status_code == 429


async def test_a_successful_sign_in_is_not_held_against_the_next_one(make_admin_app, make_admin):
    await make_admin()
    app = make_admin_app(auth_max_attempts_per_email=2)
    async with browser(app) as http:
        for _ in range(4):
            assert (await sign_in(http)).status_code == 302


# ─── The second factor ─────────────────────────────────────────────


async def test_an_admin_with_the_second_factor_must_present_a_code(
    anon, make_admin, db_session, admin_app, moving_clock
):
    admin = await make_admin()
    secret, _ = await enrol(db_session, admin_app.state.settings, admin, moving_clock)
    moving_clock.advance(minutes=5)

    missing = await sign_in(anon)
    wrong = await sign_in(anon, code="000000")
    right = await sign_in(anon, code=code_now(secret, moving_clock))

    assert (missing.status_code, wrong.status_code, right.status_code) == (401, 401, 302)
    assert REFUSED in missing.text
    assert [row.details for row in (await audit_rows(db_session))[:3]] == [
        {"reason": "code_missing"},
        {"reason": "bad_code"},
        None,
    ]


async def test_a_code_cannot_be_used_twice_and_the_password_is_checked_before_it(
    admin_app, make_admin, db_session, moving_clock
):
    admin = await make_admin()
    secret, _ = await enrol(db_session, admin_app.state.settings, admin, moving_clock)
    moving_clock.advance(minutes=5)
    code = code_now(secret, moving_clock)
    async with browser(admin_app) as first, browser(admin_app) as second:
        assert (await sign_in(first, code=code)).status_code == 302

        assert (await sign_in(second, code=code)).status_code == 401
        # A wrong password with a valid code never spends the code or says it was right.
        moving_clock.advance(seconds=30)
        fresh = code_now(secret, moving_clock)
        assert (await sign_in(second, password="wrong", code=fresh)).status_code == 401
        assert (await sign_in(second, code=fresh)).status_code == 302


async def test_a_recovery_code_signs_in_once(admin_app, make_admin, db_session, moving_clock):
    admin = await make_admin()
    _, codes = await enrol(db_session, admin_app.state.settings, admin, moving_clock)
    async with browser(admin_app) as http:
        assert (await sign_in(http, code=codes[0])).status_code == 302
        assert (await sign_in(http, code=codes[0])).status_code == 401
        assert (await sign_in(http, code=codes[1].upper())).status_code == 302


async def test_an_enrolment_that_was_started_but_not_confirmed_asks_for_no_code(
    anon, make_admin, db_session, admin_app
):
    admin = await make_admin()
    await admin_totp_service.start_enrollment(db_session, admin_app.state.settings, admin)

    assert (await sign_in(anon)).status_code == 302


async def test_a_wrong_code_is_counted_like_a_wrong_password(
    make_admin_app, make_admin, db_session, moving_clock
):
    admin = await make_admin()
    app = make_admin_app(auth_max_attempts_per_email=2)
    await enrol(db_session, app.state.settings, admin, moving_clock)
    async with browser(app) as http:
        await sign_in(http, code="000000")
        await sign_in(http, code="111111")

        blocked = await sign_in(http, code="222222")

    assert blocked.status_code == 429


# ─── Every request is checked again ────────────────────────────────


@pytest.mark.parametrize(
    "change",
    [{"is_admin": False}, {"is_active": False}, {"deleted_at": clock.utcnow()}],
    ids=["admin rights revoked", "deactivated", "deleted"],
)
async def test_an_account_that_stops_qualifying_is_out_on_its_very_next_request(
    admin, db_session, change
):
    http, user = admin
    assert (await http.get("/admin/")).status_code == 200
    for name, value in change.items():
        setattr(user, name, value)
    await db_session.flush()

    response = await http.get("/admin/user/list")

    assert response.status_code == 302
    assert response.headers["location"].endswith("/admin/login")
    assert "Max-Age=0" in response.headers["set-cookie"]
    # The dead session is deleted, and the cleared cookie sends nothing next time.
    assert await session_count(db_session) == 0
    assert (await http.get("/admin/")).headers["location"].endswith("/admin/login")


async def test_a_session_ends_after_twelve_hours(moving_clock, admin):
    http, _ = admin
    moving_clock.advance(hours=11, minutes=59)
    assert (await http.get("/admin/")).status_code == 200

    moving_clock.advance(minutes=2)

    assert (await http.get("/admin/")).status_code == 302


async def test_an_unknown_cookie_is_sent_to_the_form_and_dropped(anon):
    anon.cookies.set("__Secure-tabsira_admin", "not-a-session", path="/admin")

    response = await anon.get("/admin/")

    assert response.status_code == 302
    assert response.headers["location"].endswith("/admin/login")
    assert "Max-Age=0" in response.headers["set-cookie"]


async def test_no_cookie_is_simply_sent_to_the_form(anon):
    response = await anon.get("/admin/user/list")

    assert response.status_code == 302
    assert response.headers["location"].endswith("/admin/login")
    assert "set-cookie" not in response.headers


async def test_an_absurdly_long_cookie_is_ignored(anon):
    anon.cookies.set("__Secure-tabsira_admin", "a" * 500, path="/admin")

    response = await anon.get("/admin/")

    assert response.status_code == 302
    assert "set-cookie" not in response.headers


async def test_signing_in_again_ends_the_session_the_browser_held(
    admin_app, make_admin, db_session
):
    await make_admin()
    async with browser(admin_app) as http:
        await sign_in(http)
        old = http.cookies.get("__Secure-tabsira_admin", path="/admin")
        await sign_in(http)

        assert http.cookies.get("__Secure-tabsira_admin", path="/admin") != old
        assert await session_count(db_session) == 1
        http.cookies.set("__Secure-tabsira_admin", old, path="/admin")
        assert (await http.get("/admin/")).status_code == 302


# ─── Signing out ───────────────────────────────────────────────────


async def test_signing_out_takes_a_confirmation_and_a_post_with_the_token(admin, db_session):
    http, user = admin

    page = await http.get("/admin/logout")
    assert page.status_code == 200
    assert 'method="POST"' in page.text
    # A GET changed nothing.
    assert await session_count(db_session) == 1

    response = await http.post("/admin/logout", data={"csrf_token": token_of(page)})

    assert response.status_code == 302
    assert response.headers["location"].endswith("/admin/login")
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert await session_count(db_session) == 0
    assert (await http.get("/admin/")).status_code == 302
    assert [(row.action, row.admin_user_id) for row in await audit_rows(db_session)][-1] == (
        AuditAction.SIGN_OUT,
        user.id,
    )


@pytest.mark.parametrize("data", [{}, {"csrf_token": "forged"}])
async def test_a_sign_out_without_the_session_token_is_refused_and_changes_nothing(
    admin, db_session, data
):
    http, _ = admin

    response = await http.post("/admin/logout", data=data)

    assert response.status_code == 403
    assert await session_count(db_session) == 1
    assert (await http.get("/admin/")).status_code == 200


async def test_signing_out_when_not_signed_in_just_goes_to_the_form(anon):
    for response in (await anon.get("/admin/logout"), await anon.post("/admin/logout")):
        assert response.status_code == 302
        assert response.headers["location"].endswith("/admin/login")


# ─── Two-factor required ───────────────────────────────────────────


async def test_when_two_factor_is_required_an_admin_without_it_reaches_only_its_page(
    make_admin_app, make_admin
):
    await make_admin()
    app = make_admin_app(admin_require_two_factor=True)
    async with browser(app) as http:
        await sign_in(http)

        held = await http.get("/admin/user/list")
        page = await http.get("/admin/two-factor")
        logout = await http.get("/admin/logout")
        asset = await http.get("/admin/statics/css/tabsira-admin.css")

    assert held.status_code == 302
    assert held.headers["location"].endswith("/admin/two-factor")
    assert (page.status_code, logout.status_code, asset.status_code) == (200, 200, 200)
    assert "Signing in here requires it" in page.text


async def test_when_two_factor_is_required_an_enrolled_admin_is_not_held(
    make_admin_app, make_admin, db_session, moving_clock
):
    admin = await make_admin()
    app = make_admin_app(admin_require_two_factor=True)
    secret, _ = await enrol(db_session, app.state.settings, admin, moving_clock)
    moving_clock.advance(minutes=5)
    async with browser(app) as http:
        await sign_in(http, code=code_now(secret, moving_clock))

        assert (await http.get("/admin/user/list")).status_code == 200


async def test_the_audit_row_of_a_failed_sign_in_names_no_typed_value(anon, make_admin, db_session):
    await make_admin()

    await sign_in(anon, email="typo@example.com", password="hunter2-typed-by-mistake")

    (row,) = await audit_rows(db_session)
    serialized = repr(
        (row.admin_user_id, row.action, row.model, row.record_id, row.details, row.ip_hash)
    )
    assert "typo@example.com" not in serialized
    assert "hunter2" not in serialized


async def test_a_flood_of_refused_sign_ins_writes_one_audit_row_per_window(
    make_admin_app, make_admin, db_session
):
    await make_admin()
    app = make_admin_app(auth_max_attempts_per_email=1)
    async with browser(app) as http:
        assert (await sign_in(http, password="wrong")).status_code == 401
        for _ in range(5):
            assert (await sign_in(http)).status_code == 429

    rows = await audit_rows(db_session)
    assert [row.details for row in rows] == [{"reason": "bad_password"}, {"reason": "rate_limited"}]


async def test_a_failed_sign_in_keeps_at_most_128_characters_of_the_user_agent(
    admin_app, make_admin, db_session
):
    await make_admin()
    async with browser(admin_app) as http:
        http.headers["User-Agent"] = "a" * 500
        await sign_in(http, password="wrong")

    (row,) = await audit_rows(db_session)
    assert row.user_agent == "a" * 128
