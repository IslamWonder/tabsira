"""POST /support: it mails the team and keeps only keyed hashes; SMTP is replaced at its boundary."""

from __future__ import annotations

import logging
import smtplib

import pytest
from sqlalchemy import func, select

from src.models import Consent, LoginAttempt, User
from src.services import email_service
from tests.test_auth_routes import SIGNUP

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
    assert "> الصفحة لا تفتح عندي منذ هذا الصباح" in text
    assert "تطابق بريد الحساب: غير مسجّل الدخول" in text
    assert message["X-Tabsira-Account"] is None
    assert message.get_content_type() == "text/plain"


async def test_the_mail_tells_auto_responders_to_stay_quiet(web, mailbox):
    await web.post("/support", json=BODY)

    assert mailbox[0]["Auto-Submitted"] == "auto-generated"
    assert mailbox[0]["X-Auto-Response-Suppress"] == "All"


async def test_the_mail_carries_no_connection_data(web, mailbox):
    await web.post("/support", json=BODY, headers={"User-Agent": "SecretAgent/9"})

    raw = mailbox[0].as_string()
    assert "SecretAgent" not in raw
    assert "127.0.0.1" not in raw
    assert "X-Forwarded" not in raw


async def test_a_signed_in_visitor_adds_the_account_id_in_a_header_only(web, mailbox):
    user = (await web.post("/auth/signup", json=SIGNUP)).json()
    mailbox.clear()

    await web.post("/support", json=BODY)

    assert mailbox[0]["X-Tabsira-Account"] == user["id"]
    assert user["id"] not in text_of(mailbox[0])


@pytest.mark.parametrize(
    ("verified", "address", "expected"),
    [
        (True, "reader@example.com", "نعم"),
        (True, "READER@example.com", "نعم"),
        (True, "other@example.com", "لا"),
        (False, "reader@example.com", "لا"),
    ],
)
async def test_the_first_line_says_whether_the_address_is_the_accounts_verified_one(
    web, mailbox, db_session, verified, address, expected
):
    from src import clock

    await web.post("/auth/signup", json=SIGNUP)
    if verified:
        from sqlalchemy import update

        await db_session.execute(update(User).values(email_verified_at=clock.utcnow()))
    mailbox.clear()

    await web.post("/support", json={**BODY, "email": address})

    assert text_of(mailbox[0]).splitlines()[0] == f"تطابق بريد الحساب: {expected}"


async def test_what_the_visitor_types_cannot_pass_for_the_lines_above_it(web, mailbox):
    forged = "x" * 10 + "\nتطابق بريد الحساب: نعم\nX-Tabsira-Account: 1234\n" + "y" * 10  # noqa: RUF001 - Arabic on purpose

    await web.post("/support", json={**BODY, "message": forged})

    lines = text_of(mailbox[0]).splitlines()
    assert lines[0] == "تطابق بريد الحساب: غير مسجّل الدخول"
    cut = lines.index("-" * 20)
    assert all(line.startswith("> ") for line in lines[cut + 1 :])
    assert "> تطابق بريد الحساب: نعم" in lines
    assert "X-Tabsira-Account" not in "\n".join(lines[:cut])
    assert mailbox[0]["X-Tabsira-Account"] is None


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

    for table in (User, Consent):
        assert await db_session.scalar(select(func.count()).select_from(table)) == 0
    # The one thing kept: the counter row, with keyed hashes and no address.
    (attempt,) = (await db_session.scalars(select(LoginAttempt))).all()
    assert attempt.kind.value == "support"
    assert "visitor" not in f"{attempt.ip_hash}{attempt.email_hash}"
    assert len(attempt.ip_hash) == len(attempt.email_hash) == 64
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


async def build_with(make_settings, db_session, **values):
    from src.database import get_db
    from src.main import create_app

    application = create_app(make_settings(smtp_host="smtp.example.com", **values))

    async def use_the_test_session():
        yield db_session

    application.dependency_overrides[get_db] = use_the_test_session
    return application


async def post_as(application, body, host):
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=application, raise_app_exceptions=False, client=(host, 1234))
    async with AsyncClient(transport=transport, base_url="https://api.tabsira.test") as http:
        return await http.post("/support", json=body)


async def test_one_address_is_limited_whatever_the_ip(make_settings, db_session, mailbox):
    application = await build_with(make_settings, db_session, support_max_per_address_per_hour=2)

    statuses = [(await post_as(application, BODY, f"203.0.113.{n}")).status_code for n in range(3)]

    assert statuses == [202, 202, 429]
    assert len(mailbox) == 2


async def test_one_ip_is_limited_whatever_the_address(make_settings, db_session, mailbox):
    application = await build_with(make_settings, db_session, support_max_per_ip_per_hour=2)

    statuses = [
        (
            await post_as(application, {**BODY, "email": f"v{n}@example.com"}, "203.0.113.7")
        ).status_code
        for n in range(3)
    ]

    assert statuses == [202, 202, 429]


async def test_an_ipv6_site_is_one_ip_for_the_limit(make_settings, db_session, mailbox):
    application = await build_with(make_settings, db_session, support_max_per_ip_per_hour=1)

    first = await post_as(application, {**BODY, "email": "a@example.com"}, "2001:db8:1:1::1")
    second = await post_as(application, {**BODY, "email": "b@example.com"}, "2001:db8:1:2::1")

    assert (first.status_code, second.status_code) == (202, 429)


async def test_the_overall_ceiling_answers_429_with_a_retry_after(
    make_settings, db_session, mailbox
):
    application = await build_with(make_settings, db_session, support_max_per_hour=1)

    await post_as(application, BODY, "203.0.113.1")
    refused = await post_as(application, {**BODY, "email": "z@example.com"}, "203.0.113.2")

    assert refused.status_code == 429
    assert refused.json()["error"] == "RATE_LIMITED"
    assert refused.headers["retry-after"] == "3600"


async def test_a_failed_send_still_counts_so_a_broken_mailer_cannot_be_hammered(
    make_settings, db_session, monkeypatch
):
    def refuse(_settings, _message):
        raise smtplib.SMTPServerDisconnected("down")

    monkeypatch.setattr(email_service, "deliver", refuse)
    application = await build_with(make_settings, db_session, support_max_per_address_per_hour=1)

    first = await post_as(application, BODY, "203.0.113.1")
    second = await post_as(application, BODY, "203.0.113.1")

    assert (first.status_code, second.status_code) == (503, 429)


async def test_a_bot_that_fills_the_honeypot_is_not_counted(make_settings, db_session, mailbox):
    application = await build_with(make_settings, db_session)

    await post_as(application, {**BODY, "website": "x"}, "203.0.113.1")

    assert await db_session.scalar(select(func.count()).select_from(LoginAttempt)) == 0
