"""E-mail verification and password reset, end to end through the routes and the mailbox."""

from __future__ import annotations

import logging

import pytest
from sqlalchemy import select

from src.models import EmailToken, Session, User
from tests.conftest import PASSPHRASE

LOGIN = {"email": "reader@example.com", "password": PASSPHRASE}


def link_token(message) -> str:
    text = message.get_body(preferencelist=("plain",)).get_content()
    return text.split("#token=")[1].split()[0]


async def request_reset(web, mailbox, email="reader@example.com"):
    mailbox.clear()
    response = await web.post("/auth/forgot-password", json={"email": email})
    return response, (link_token(mailbox[0]) if mailbox else None)


# ─── Verification ─────────────────────────────────────────────────────────────


async def test_the_resent_verification_link_verifies_once_and_then_is_spent(
    web, make_user, mailbox
):
    await make_user()

    resent = await web.post("/auth/resend-verification", json={"email": "reader@example.com"})
    token = link_token(mailbox[0])
    first = await web.post("/auth/verify-email", json={"token": token})
    second = await web.post("/auth/verify-email", json={"token": token})

    assert resent.status_code == 202
    assert first.status_code == 200
    assert first.json() == {"status": "ok"}
    assert second.status_code == 400
    assert second.json()["error"] == "INVALID_TOKEN"


async def test_a_new_verification_link_cancels_the_earlier_one(web, make_user, mailbox):
    await make_user()
    await web.post("/auth/resend-verification", json={"email": "reader@example.com"})
    await web.post("/auth/resend-verification", json={"email": "reader@example.com"})
    old, new = link_token(mailbox[0]), link_token(mailbox[1])

    assert (await web.post("/auth/verify-email", json={"token": old})).status_code == 400
    assert (await web.post("/auth/verify-email", json={"token": new})).status_code == 200


async def test_every_bad_verification_token_gets_the_same_answer(
    web, make_user, mailbox, moving_clock
):
    await make_user()
    await web.post("/auth/resend-verification", json={"email": "reader@example.com"})
    expired = link_token(mailbox[0])
    moving_clock.advance(hours=25)

    answers = [
        await web.post("/auth/verify-email", json={"token": token})
        for token in (expired, "x" * 43, "this-token-was-never-issued-at-all")
    ]

    assert {response.status_code for response in answers} == {400}
    assert len({response.text for response in answers}) == 1


async def test_a_reset_token_cannot_verify_an_address_and_is_not_spent_by_trying(
    web, make_user, mailbox
):
    await make_user()
    _, reset_token = await request_reset(web, mailbox)

    assert (await web.post("/auth/verify-email", json={"token": reset_token})).status_code == 400
    assert (
        await web.post(
            "/auth/reset-password", json={"token": reset_token, "password": "a new password"}
        )
    ).status_code == 200


async def test_a_token_that_is_too_short_or_missing_is_a_422(web):
    assert (await web.post("/auth/verify-email", json={"token": "short"})).status_code == 422
    assert (await web.post("/auth/verify-email", json={})).status_code == 422
    assert (await web.post("/auth/verify-email", json={"token": "x" * 300})).status_code == 422


async def test_redeeming_links_is_rate_limited_per_ip(web):
    statuses = [
        (await web.post("/auth/verify-email", json={"token": f"{n:0>40}"})).status_code
        for n in range(22)
    ]

    assert statuses == [400] * 20 + [429, 429]


async def test_resending_mails_only_an_account_that_exists_and_is_unverified(
    web, make_user, mailbox
):
    await make_user("unverified@example.com")
    await make_user("verified@example.com", verified=True)
    await make_user("disabled@example.com", is_active=False)

    answers = [
        await web.post("/auth/resend-verification", json={"email": email})
        for email in (
            "unverified@example.com",
            "verified@example.com",
            "disabled@example.com",
            "nobody@example.com",
        )
    ]

    assert {response.status_code for response in answers} == {202}
    assert len({response.text for response in answers}) == 1
    assert [message["To"] for message in mailbox] == ["unverified@example.com"]


async def test_resending_is_limited_per_address_and_per_ip_and_still_says_nothing_about_the_address(
    web, make_user, mailbox
):
    await make_user()
    per_address = [
        (
            await web.post("/auth/resend-verification", json={"email": "reader@example.com"})
        ).status_code
        for _ in range(6)
    ]
    per_ip = [
        (
            await web.post("/auth/resend-verification", json={"email": f"n{n}@example.com"})
        ).status_code
        for n in range(16)
    ]

    assert per_address == [202] * 5 + [429]
    # 20 are allowed per IP in the window; the 5 accepted above count, a refused one does not.
    assert per_ip == [202] * 15 + [429]


# ─── Password reset ───────────────────────────────────────────────────────────


async def test_forgot_password_answers_202_whether_or_not_the_address_exists(
    web, make_user, mailbox
):
    await make_user()

    known = await web.post("/auth/forgot-password", json={"email": "reader@example.com"})
    unknown = await web.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    disabled = await make_user("off@example.com", is_active=False)
    off = await web.post("/auth/forgot-password", json={"email": disabled.email})

    assert (known.status_code, unknown.status_code, off.status_code) == (202, 202, 202)
    assert known.text == unknown.text == off.text
    assert [message["To"] for message in mailbox] == ["reader@example.com"]


async def test_the_reset_mail_is_arabic_and_its_link_sets_a_new_password(web, make_user, mailbox):
    await make_user()

    _, token = await request_reset(web, mailbox)

    (message,) = mailbox
    assert message["Subject"] == "إعادة تعيين كلمة المرور في تبصرة"
    assert "/reset-password#token=" in message.get_body(preferencelist=("plain",)).get_content()
    reset = await web.post(
        "/auth/reset-password", json={"token": token, "password": "a brand new password"}
    )
    assert reset.status_code == 200
    assert (await web.post("/auth/login", json=LOGIN)).status_code == 401
    assert (
        await web.post("/auth/login", json={**LOGIN, "password": "a brand new password"})
    ).status_code == 200


async def test_a_reset_token_works_once(web, make_user, mailbox):
    await make_user()
    _, token = await request_reset(web, mailbox)
    body = {"token": token, "password": "a brand new password"}

    assert (await web.post("/auth/reset-password", json=body)).status_code == 200
    again = await web.post("/auth/reset-password", json={**body, "password": "yet another one!"})

    assert again.status_code == 400
    assert again.json()["error"] == "INVALID_TOKEN"


async def test_a_second_reset_request_cancels_the_first_link(web, make_user, mailbox):
    await make_user()
    _, first = await request_reset(web, mailbox)
    _, second = await request_reset(web, mailbox)
    body = {"password": "a brand new password"}

    assert (
        await web.post("/auth/reset-password", json={**body, "token": first})
    ).status_code == 400
    assert (
        await web.post("/auth/reset-password", json={**body, "token": second})
    ).status_code == 200


async def test_a_reset_link_expires(web, make_user, mailbox, moving_clock):
    await make_user()
    _, token = await request_reset(web, mailbox)
    moving_clock.advance(minutes=61)

    response = await web.post(
        "/auth/reset-password", json={"token": token, "password": "a brand new password"}
    )

    assert response.status_code == 400


async def test_a_reset_ends_every_other_session_but_not_the_one_that_followed_the_link(
    web, make_user, mailbox, db_session, account_app
):
    from tests.conftest import browser_for

    await make_user()
    await web.post("/auth/login", json=LOGIN)
    async with browser_for(account_app) as phone:
        await phone.post("/auth/login", json=LOGIN)
        _, token = await request_reset(web, mailbox)

        reset = await web.post(
            "/auth/reset-password", json={"token": token, "password": "a brand new password"}
        )

        assert reset.status_code == 200
        assert (await web.get("/auth/me")).status_code == 200
        assert (await phone.get("/auth/me")).status_code == 401
    assert len((await db_session.scalars(select(Session))).all()) == 1


async def test_a_reset_with_no_session_ends_all_of_them(
    web, make_user, mailbox, db_session, account_app
):
    from tests.conftest import browser_for

    await make_user()
    async with browser_for(account_app) as phone:
        await phone.post("/auth/login", json=LOGIN)
        _, token = await request_reset(web, mailbox)

        await web.post(
            "/auth/reset-password", json={"token": token, "password": "a brand new password"}
        )

        assert (await phone.get("/auth/me")).status_code == 401


async def test_following_a_reset_link_proves_the_address(web, make_user, mailbox, db_session):
    await make_user(verified=False)
    _, token = await request_reset(web, mailbox)

    await web.post(
        "/auth/reset-password", json={"token": token, "password": "a brand new password"}
    )

    assert (await db_session.scalar(select(User))).email_verified_at is not None


async def test_a_reset_gives_a_google_only_account_a_password_too(web, make_user, mailbox):
    await make_user("google@example.com", password=None)
    _, token = await request_reset(web, mailbox, "google@example.com")

    await web.post(
        "/auth/reset-password", json={"token": token, "password": "a brand new password"}
    )

    login = await web.post(
        "/auth/login", json={"email": "google@example.com", "password": "a brand new password"}
    )
    assert login.status_code == 200
    assert login.json()["has_password"] is True


async def test_a_reset_refuses_a_weak_password_without_spending_the_link(web, make_user, mailbox):
    await make_user()
    _, token = await request_reset(web, mailbox)

    weak = await web.post("/auth/reset-password", json={"token": token, "password": "short"})
    ok = await web.post(
        "/auth/reset-password", json={"token": token, "password": "a brand new password"}
    )

    assert weak.status_code == 422
    assert "short" not in weak.json()["detail"]
    assert ok.status_code == 200


async def test_a_reset_link_of_an_account_that_was_disabled_since_is_refused(
    web, make_user, mailbox, db_session
):
    user = await make_user()
    _, token = await request_reset(web, mailbox)
    user.is_active = False
    await db_session.flush()

    response = await web.post(
        "/auth/reset-password", json={"token": token, "password": "a brand new password"}
    )

    assert response.status_code == 400


async def test_forgot_password_is_limited_per_address_and_per_ip(web, make_user, mailbox):
    await make_user()
    per_address = [
        (await web.post("/auth/forgot-password", json={"email": "reader@example.com"})).status_code
        for _ in range(6)
    ]

    assert per_address == [202] * 5 + [429]
    assert len(mailbox) == 5


async def test_a_token_in_the_database_is_a_hash_and_the_mailed_token_is_in_no_log(
    web, make_user, mailbox, db_session, caplog
):
    await make_user()
    with caplog.at_level(logging.DEBUG):
        _, token = await request_reset(web, mailbox)
        await web.post(
            "/auth/reset-password", json={"token": token, "password": "a brand new password"}
        )

    stored = (await db_session.scalars(select(EmailToken))).all()
    assert stored
    assert all(token.encode() not in row.token_hash for row in stored)
    assert token not in caplog.text
    assert "a brand new password" not in caplog.text


async def test_without_smtp_forgot_password_still_answers_202_and_the_api_logs_an_error(
    make_settings, db_session, caplog, make_user
):
    from src.database import get_db
    from src.main import create_app
    from tests.conftest import browser_for

    application = create_app(make_settings(password_bcrypt_rounds=4, smtp_host=""))

    async def use_session():
        yield db_session

    application.dependency_overrides[get_db] = use_session
    await make_user()

    with caplog.at_level(logging.ERROR, logger="tabsira.email"):
        async with browser_for(application) as client:
            known = await client.post("/auth/forgot-password", json={"email": "reader@example.com"})
            unknown = await client.post(
                "/auth/forgot-password", json={"email": "nobody@example.com"}
            )

    assert (known.status_code, unknown.status_code) == (202, 202)
    assert known.text == unknown.text
    assert caplog.text.count("SMTP is not configured") == 1
    assert "reader@example.com" not in caplog.text


@pytest.mark.parametrize("path", ["/auth/resend-verification", "/auth/forgot-password"])
async def test_the_mail_routes_refuse_a_bad_address(web, path):
    assert (await web.post(path, json={"email": "nope"})).status_code == 422
    assert (await web.post(path, json={"email": "a@example.com", "x": 1})).status_code == 422


async def test_a_link_for_an_address_that_is_already_verified_still_answers_ok_and_keeps_the_date(
    web, make_user, mailbox, db_session, moving_clock
):
    user = await make_user(verified=False)
    await web.post("/auth/resend-verification", json={"email": "reader@example.com"})
    token = link_token(mailbox[0])
    verified_at = moving_clock.now
    user.email_verified_at = verified_at  # proven another way since, e.g. through Google
    await db_session.flush()
    moving_clock.advance(hours=1)

    response = await web.post("/auth/verify-email", json={"token": token})

    assert response.status_code == 200
    assert user.email_verified_at == verified_at


async def test_a_reset_for_an_address_that_is_already_verified_keeps_the_date(
    web, make_user, mailbox, moving_clock
):
    user = await make_user(verified=True)
    verified_at = user.email_verified_at
    moving_clock.advance(hours=1)
    _, token = await request_reset(web, mailbox)

    await web.post(
        "/auth/reset-password", json={"token": token, "password": "a brand new password"}
    )

    assert user.email_verified_at == verified_at
