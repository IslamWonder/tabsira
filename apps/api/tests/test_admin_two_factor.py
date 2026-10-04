"""The page where an admin turns the second factor on and off, step by step."""

from __future__ import annotations

import re

import pyotp
import pytest

from src.models import AdminTotp, AuditAction
from src.services import admin_totp_service
from tests.support_admin import audit_rows, csrf_of

PAGE = "/admin/two-factor"


async def post(http, path, **data):
    return await http.post(f"{PAGE}/{path}", data={"csrf_token": await csrf_of(http), **data})


async def stored(db_session, user):
    return await admin_totp_service.get(db_session, user.id)


def secret_on(page):
    """Read the secret the page shows for typing into an app: groups of four, spaces between."""
    found = re.search(r'id="totp-secret">([A-Z2-7 ]+)<', page.text)
    assert found, page.text
    return found.group(1).replace(" ", "")


def code_for(secret, moving_clock):
    return pyotp.TOTP(secret).at(int(moving_clock.now.timestamp()))


async def start(http):
    response = await post(http, "start")
    assert response.status_code == 303
    return await http.get(PAGE)


async def enable(http, moving_clock):
    page = await start(http)
    secret = secret_on(page)
    response = await post(http, "confirm", code=code_for(secret, moving_clock))
    assert response.status_code == 200
    return secret, response


# ─── Off, started, on ──────────────────────────────────────────────


async def test_the_page_starts_with_the_factor_off_and_one_button(admin):
    http, _ = admin

    page = await http.get(PAGE)

    assert page.status_code == 200
    assert "Two-factor sign-in is off" in page.text
    assert f"{PAGE}/start" in page.text
    assert "totp-secret" not in page.text


async def test_starting_shows_a_key_to_type_into_the_app_and_stores_it_encrypted(
    admin, db_session, admin_app
):
    http, user = admin

    page = await start(http)

    secret = secret_on(page)
    assert "otpauth://totp/" in page.text
    assert f"secret={secret}" in page.text
    row = await stored(db_session, user)
    assert row is not None
    assert row.enabled_at is None
    assert secret not in row.secret_encrypted
    assert (
        admin_totp_service.decrypt_secret(admin_app.state.settings, row.secret_encrypted) == secret
    )


async def test_starting_again_before_confirming_gives_a_new_key(admin):
    http, _ = admin

    first = secret_on(await start(http))
    second = secret_on(await start(http))

    assert first != second


async def test_a_wrong_first_code_keeps_the_enrolment_pending_and_says_so(
    admin, db_session, moving_clock
):
    http, user = admin
    await start(http)

    response = await post(http, "confirm", code="000000")

    assert response.status_code == 400
    assert "That code is wrong." in response.text
    row = await stored(db_session, user)
    assert row is not None
    assert row.enabled_at is None


async def test_the_right_first_code_turns_it_on_and_shows_the_recovery_codes_once(
    admin, db_session, moving_clock
):
    http, user = admin

    _, response = await enable(http, moving_clock)

    codes = re.findall(r"\b[0-9a-f]{4}(?:-[0-9a-f]{4}){3}\b", response.text)
    assert len(codes) == admin_totp_service.RECOVERY_CODE_COUNT
    assert "Keep these recovery codes" in response.text
    row = await stored(db_session, user)
    assert row is not None
    assert admin_totp_service.is_enabled(row)
    assert not set(codes) & set(row.recovery_hashes)
    # The next visit shows the state, not the codes.
    again = await http.get(PAGE)
    assert not re.search(r"[0-9a-f]{4}(?:-[0-9a-f]{4}){3}", again.text)
    assert "10 recovery codes left" in again.text
    rows = await audit_rows(db_session)
    assert rows[-1].action is AuditAction.TWO_FACTOR_ENABLED
    assert rows[-1].admin_user_id == user.id


async def test_confirming_without_starting_is_refused(admin):
    http, _ = admin

    response = await post(http, "confirm", code="123456")

    assert response.status_code == 400
    assert "Start the enrolment first." in response.text


async def test_an_enrolled_admin_cannot_start_over_without_switching_it_off(admin, moving_clock):
    http, _ = admin
    await enable(http, moving_clock)

    response = await post(http, "start")

    assert response.status_code == 400
    assert "already on" in response.text


async def test_confirming_twice_is_refused_the_second_time(admin, moving_clock):
    http, _ = admin
    secret, _ = await enable(http, moving_clock)
    moving_clock.advance(seconds=30)

    response = await post(http, "confirm", code=code_for(secret, moving_clock))

    assert response.status_code == 400


# ─── Switching it off ──────────────────────────────────────────────


async def test_switching_off_needs_a_current_code_and_removes_everything(
    admin, db_session, moving_clock
):
    http, user = admin
    secret, _ = await enable(http, moving_clock)
    moving_clock.advance(minutes=2)

    wrong = await post(http, "disable", code="000000")
    right = await post(http, "disable", code=code_for(secret, moving_clock))

    assert wrong.status_code == 400
    assert right.status_code == 303
    assert await stored(db_session, user) is None
    assert "Two-factor sign-in is off" in (await http.get(PAGE)).text
    rows = await audit_rows(db_session)
    assert rows[-1].action is AuditAction.TWO_FACTOR_DISABLED


async def test_a_recovery_code_switches_it_off_too(admin, db_session, moving_clock):
    http, user = admin
    _, response = await enable(http, moving_clock)
    code = re.findall(r"\b[0-9a-f]{4}(?:-[0-9a-f]{4}){3}\b", response.text)[0]

    result = await post(http, "disable", code=code)

    assert result.status_code == 303
    assert await stored(db_session, user) is None


async def test_switching_off_is_rate_limited_like_a_sign_in(
    make_admin_app, make_admin, moving_clock
):
    from tests.support_admin import browser, sign_in

    await make_admin()
    app = make_admin_app(auth_max_attempts_per_email=2)
    async with browser(app) as http:
        await sign_in(http)
        await enable(http, moving_clock)
        await post(http, "disable", code="000000")
        await post(http, "disable", code="111111")

        blocked = await post(http, "disable", code="222222")

    assert blocked.status_code == 429
    assert "Too many attempts" in blocked.text


# ─── The rules the page shares with every other ────────────────────


@pytest.mark.parametrize("step", ["start", "confirm", "disable"])
async def test_every_step_needs_the_csrf_token(admin, step):
    http, _ = admin

    response = await http.post(f"{PAGE}/{step}", data={"code": "123456"})

    assert response.status_code == 403


async def test_a_signed_out_browser_gets_the_form(anon):
    for response in (await anon.get(PAGE), await anon.post(f"{PAGE}/start")):
        assert response.status_code == 302
        assert response.headers["location"].endswith("/admin/login")


async def test_a_secret_the_keys_cannot_open_is_not_shown(admin, db_session, admin_app):
    http, user = admin
    await start(http)
    row = await stored(db_session, user)
    assert isinstance(row, AdminTotp)
    row.secret_encrypted = "gAAAAA-not-a-token-this-key-can-open"
    await db_session.flush()

    page = await http.get(PAGE)

    assert page.status_code == 200
    assert "totp-secret" not in page.text
    assert "Two-factor sign-in is off" in page.text
