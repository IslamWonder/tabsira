"""POST /support: it mails the team and stores nothing; mail is replaced at the SMTP boundary."""

from __future__ import annotations

import logging
import smtplib

import pytest
from sqlalchemy import func, select

from src.models import Consent, LoginAttempt, User
from src.services import email_service
from src.services.window_limiter import AddressLimits
from tests.test_auth_routes import LOGIN, SIGNUP

BODY = {
    "email": "visitor@example.com",
    "name": "  ليلى  ",
    "topic": "bug",
    "message": "  الصفحة لا تفتح عندي منذ هذا الصباح  ",
}


def text_of(message):
    return message.get_content()


async def test_a_message_is_mailed_to_support_with_the_visitor_as_reply_to(web, mailbox):
    response = await web.post("/support", json=BODY)

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    (message,) = mailbox
    assert message["To"] == "support@tabsira.me"
    assert message["Reply-To"] == "visitor@example.com"
    assert message["Subject"] == "[تبصرة] مشكلة تقنية"
    text = text_of(message)
    assert "الاسم: ليلى" in text
    assert "البريد: visitor@example.com" in text
    assert "الموضوع: مشكلة تقنية" in text
    assert "الصفحة لا تفتح عندي منذ هذا الصباح" in text
    assert "رقم الحساب" not in text
    assert message.get_content_type() == "text/plain"


async def test_the_mail_carries_no_connection_data(web, mailbox):
    await web.post("/support", json=BODY, headers={"User-Agent": "SecretAgent/9"})

    raw = mailbox[0].as_string()
    assert "SecretAgent" not in raw
    assert "127.0.0.1" not in raw
    assert "X-Forwarded" not in raw


async def test_a_signed_in_visitor_adds_the_account_id(web, mailbox):
    user = (await web.post("/auth/signup", json=SIGNUP)).json()
    mailbox.clear()

    await web.post("/support", json=BODY)

    assert f"رقم الحساب: {user['id']}" in text_of(mailbox[0])


async def test_a_missing_name_is_a_dash(web, mailbox):
    await web.post("/support", json={**BODY, "name": None})

    assert "الاسم: -" in text_of(mailbox[0])


async def test_a_filled_honeypot_is_accepted_and_sends_nothing(web, mailbox):
    response = await web.post("/support", json={**BODY, "website": "http://spam.example"})

    assert response.status_code == 202
    assert mailbox == []


async def test_nothing_is_stored_and_nothing_is_logged(web, mailbox, db_session, caplog):
    caplog.set_level(logging.DEBUG)

    await web.post("/support", json=BODY)

    for table in (User, Consent, LoginAttempt):
        assert await db_session.scalar(select(func.count()).select_from(table)) == 0
    assert "visitor@example.com" not in caplog.text
    assert "الصفحة" not in caplog.text


@pytest.mark.parametrize(
    "changes",
    [
        {"email": "not an address"},
        {"email": "a@example.com\nBcc: x@example.com"},
        {"topic": "billing"},
        {"message": "too short"},
        {"message": " " * 30},
        {"message": "x" * 4001},
        {"name": "x" * 161},
        {"name": "a" * 81},
        {"name": "bad\u202ename"},
        {"unknown": 1},
    ],
)
async def test_a_bad_form_is_a_422_and_sends_nothing(web, mailbox, changes):
    response = await web.post("/support", json={**BODY, **changes})

    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"
    assert mailbox == []


async def test_a_blank_name_is_treated_as_none(web, mailbox):
    await web.post("/support", json={**BODY, "name": "   "})

    assert "الاسم: -" in text_of(mailbox[0])


async def test_the_body_is_limited_to_eight_kib(web, mailbox):
    response = await web.post("/support", json={**BODY, "website": "x" * 9000})

    assert response.status_code == 413
    assert mailbox == []


async def test_without_smtp_the_answer_is_503_mail_unavailable(make_settings, db_session, caplog):
    from src.database import get_db
    from src.main import create_app
    from tests.conftest import browser_for

    application = create_app(make_settings(smtp_host=""))

    async def use_the_test_session():
        yield db_session

    application.dependency_overrides[get_db] = use_the_test_session
    async with browser_for(application) as http:
        response = await http.post("/support", json=BODY)

    assert response.status_code == 503
    assert response.json()["error"] == "mail_unavailable"
    assert "visitor@example.com" not in caplog.text


async def test_a_failed_send_is_a_503_that_logs_only_the_kind_of_error(web, monkeypatch, caplog):
    def refuse(_settings, _message):
        raise smtplib.SMTPRecipientsRefused({"visitor@example.com": (550, b"no such user")})

    monkeypatch.setattr(email_service, "deliver", refuse)

    response = await web.post("/support", json=BODY)

    assert response.status_code == 503
    assert response.json()["error"] == "mail_unavailable"
    assert "SMTPRecipientsRefused" in caplog.text
    assert "visitor@example.com" not in caplog.text
    assert "no such user" not in caplog.text


async def test_the_limit_per_address_and_overall_answer_429(account_app, web, mailbox):
    account_app.state.support_limits = AddressLimits(2, 3, 3600)

    statuses = [(await web.post("/support", json=BODY)).status_code for _ in range(3)]

    assert statuses == [202, 202, 429]
    assert (await web.post("/support", json=BODY)).headers["retry-after"]
    assert len(mailbox) == 2


async def test_the_limits_come_from_the_settings(make_settings, db_session, mailbox):
    from src.database import get_db
    from src.main import create_app
    from tests.conftest import browser_for

    application = create_app(
        make_settings(smtp_host="smtp.example.com", support_max_per_address_per_hour=1)
    )

    async def use_the_test_session():
        yield db_session

    application.dependency_overrides[get_db] = use_the_test_session
    async with browser_for(application) as http:
        first = await http.post("/support", json=BODY)
        second = await http.post("/support", json=BODY)

    assert (first.status_code, second.status_code) == (202, 429)
    assert second.json()["error"] == "RATE_LIMITED"


async def test_a_login_cookie_is_not_needed_and_login_fixture_unused(web, mailbox):
    assert LOGIN  # the route answers a guest; this keeps the import honest
    assert (await web.post("/support", json=BODY)).status_code == 202
