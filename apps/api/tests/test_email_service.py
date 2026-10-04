from __future__ import annotations

import logging
import smtplib
import ssl
from email import message_from_bytes, policy

import pytest

from src.services import email_service

EXAMPLE_TOKEN = "tok/en+with=unsafe chars"


@pytest.fixture
def settings(make_settings):
    return make_settings(
        smtp_host="smtp.example.com",
        smtp_username="mailer",
        smtp_password="mailer-password",
        mail_reply_to="help@tabsira.me",
        site_url="https://tabsira.example",
    )


def body_of(message, kind):
    part = message.get_body(preferencelist=(kind,))
    return part.get_content()


async def test_the_verification_mail_is_arabic_rtl_with_a_text_and_an_html_part(settings):
    message = email_service.build_message(
        settings,
        to="reader@example.com",
        subject="s",
        template="verify_email",
        context={"name": "ليلى", "verify_url": "https://x.example/#token=t", "expires_hours": 24},
    )

    html, text = body_of(message, "html"), body_of(message, "plain")

    assert message["From"] == "تبصرة <no-reply@tabsira.me>"
    assert message["To"] == "reader@example.com"
    assert message["Reply-To"] == "help@tabsira.me"
    assert message["Auto-Submitted"] == "auto-generated"
    assert message["Message-ID"].endswith("@tabsira.me>")
    assert message["Date"]
    assert 'lang="ar" dir="rtl"' in html
    assert "مرحبًا ليلى" in html
    assert "مرحبًا ليلى" in text
    assert "https://x.example/#token=t" in html
    assert "https://x.example/#token=t" in text
    assert "24 ساعة" in html
    assert "help@tabsira.me" in html
    assert "help@tabsira.me" in text
    assert [part.get_content_type() for part in message.iter_parts()] == [
        "text/plain",
        "text/html",
    ]


async def test_a_display_name_cannot_inject_markup_into_the_html_part(settings):
    name = '<script>alert(1)</script> & "quotes"'

    message = email_service.build_message(
        settings,
        to="a@example.com",
        subject="s",
        template="password_reset",
        context={"name": name, "reset_url": "https://x.example/#token=t", "expires_minutes": 60},
    )

    html, text = body_of(message, "html"), body_of(message, "plain")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    # The plain-text part is not HTML and keeps the name as written.
    assert name in text


def test_a_reply_to_is_added_only_when_one_is_configured(make_settings):
    quiet = make_settings(smtp_host="smtp.example.com", mail_reply_to="")

    message = email_service.build_message(
        quiet,
        to="a@example.com",
        subject="s",
        template="password_reset",
        context={"name": "n", "reset_url": "u", "expires_minutes": 1},
    )

    assert message["Reply-To"] is None
    assert "للمساعدة اكتب" not in body_of(message, "plain")


def test_the_link_keeps_the_token_in_the_fragment_and_escapes_it(settings):
    link = email_service.link(settings, "/reset-password", EXAMPLE_TOKEN)

    assert link == "https://tabsira.example/reset-password#token=tok%2Fen%2Bwith%3Dunsafe%20chars"
    assert "?" not in link


def test_the_link_uses_the_web_base_url_when_there_is_one(make_settings):
    settings = make_settings(web_base_url="https://web.example")

    assert (
        email_service.link(settings, "/verify-email", "t")
        == "https://web.example/verify-email#token=t"
    )


async def test_nothing_is_sent_without_an_smtp_host_and_the_api_logs_an_error(
    make_settings, mailbox, caplog
):
    settings = make_settings(smtp_host="")

    with caplog.at_level(logging.ERROR, logger="tabsira.email"):
        sent = await email_service.send_email_verification(
            settings, email="secret-address@example.com", name="n", token="secret-token"
        )

    assert sent is False
    assert mailbox == []
    assert "SMTP is not configured" in caplog.text
    assert "secret-address" not in caplog.text
    assert "secret-token" not in caplog.text


async def test_a_mail_is_built_and_handed_to_the_server(settings, mailbox, caplog):
    with caplog.at_level(logging.INFO, logger="tabsira.email"):
        verified = await email_service.send_email_verification(
            settings, email="reader@example.com", name="ليلى", token=EXAMPLE_TOKEN
        )
        reset = await email_service.send_password_reset(
            settings, email="reader@example.com", name="ليلى", token=EXAMPLE_TOKEN
        )

    assert verified is True
    assert reset is True
    assert [message["Subject"] for message in mailbox] == [
        "أكّد بريدك الإلكتروني في تبصرة",
        "إعادة تعيين كلمة المرور في تبصرة",
    ]
    assert "/verify-email#token=" in body_of(mailbox[0], "plain")
    assert "/reset-password#token=" in body_of(mailbox[1], "plain")
    assert "60 دقيقة" in body_of(mailbox[1], "plain")
    assert "Sent email verification" in caplog.text
    assert "reader@example.com" not in caplog.text
    assert EXAMPLE_TOKEN not in caplog.text


async def test_a_failed_send_is_logged_without_the_address_or_the_token_and_never_raised(
    settings, monkeypatch, caplog
):
    def refuse(_settings, _message):
        raise smtplib.SMTPRecipientsRefused({"reader@example.com": (550, b"no such user")})

    monkeypatch.setattr(email_service, "deliver", refuse)

    with caplog.at_level(logging.ERROR, logger="tabsira.email"):
        sent = await email_service.send_password_reset(
            settings, email="reader@example.com", name="n", token=EXAMPLE_TOKEN
        )

    assert sent is False
    assert "Failed to send password reset: SMTPRecipientsRefused" in caplog.text
    assert "550" in caplog.text
    assert "reader@example.com" not in caplog.text
    assert "<recipient>" in caplog.text
    assert EXAMPLE_TOKEN not in caplog.text


def test_a_long_failure_text_is_cut():
    text = email_service.describe_failure(RuntimeError("x" * 1000), "a@example.com")

    assert len(text) == email_service.FAILURE_TEXT_MAX


# ─── The SMTP conversation itself, against a stand-in for smtplib ──────────────


class FakeSmtp:
    """Stands in for smtplib.SMTP and SMTP_SSL: records the conversation, opens no socket."""

    instances: list[FakeSmtp] = []
    fail_starttls = False

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.calls = []
        self.closed = False
        FakeSmtp.instances.append(self)

    def starttls(self, context):
        self.calls.append(("starttls", context))
        if FakeSmtp.fail_starttls:
            message = "STARTTLS extension not supported by server."
            raise smtplib.SMTPNotSupportedError(message)

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, message):
        self.calls.append(("send", message["To"]))

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True


@pytest.fixture
def smtp(monkeypatch):
    FakeSmtp.instances = []
    FakeSmtp.fail_starttls = False
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSmtp)
    return FakeSmtp


def a_message(settings):
    return email_service.build_message(
        settings,
        to="reader@example.com",
        subject="s",
        template="password_reset",
        context={"name": "n", "reset_url": "u", "expires_minutes": 1},
    )


def test_starttls_encrypts_before_logging_in_and_sending(settings, smtp):
    email_service.deliver(settings, a_message(settings))

    (server,) = smtp.instances
    assert (server.host, server.port, server.timeout) == ("smtp.example.com", 587, 15.0)
    assert [call[0] for call in server.calls] == ["starttls", "login", "send"]
    assert server.calls[1] == ("login", "mailer", "mailer-password")
    assert isinstance(server.calls[0][1], ssl.SSLContext)
    assert server.calls[0][1].verify_mode == ssl.CERT_REQUIRED
    assert server.closed


def test_ssl_security_connects_with_tls_from_the_start(make_settings, smtp):
    settings = make_settings(smtp_host="smtp.example.com", smtp_port=465, smtp_security="ssl")

    email_service.deliver(settings, a_message(settings))

    (server,) = smtp.instances
    assert server.port == 465
    assert isinstance(server.context, ssl.SSLContext)
    # No login when there is no username, and no STARTTLS on an already encrypted line.
    assert [call[0] for call in server.calls] == ["send"]


def test_a_server_without_starttls_is_an_error_and_never_a_clear_text_send(settings, smtp):
    smtp.fail_starttls = True

    with pytest.raises(smtplib.SMTPNotSupportedError):
        email_service.deliver(settings, a_message(settings))

    (server,) = smtp.instances
    assert [call[0] for call in server.calls] == ["starttls"]
    assert server.closed


def test_a_private_ca_file_is_trusted_for_the_connection(
    make_settings, smtp, monkeypatch, tmp_path
):
    ca = tmp_path / "ca.pem"
    ca.write_text("-")
    real, seen = ssl.create_default_context, {}

    def spy(cafile=None):
        seen["cafile"] = cafile
        return real()

    monkeypatch.setattr(ssl, "create_default_context", spy)
    settings = make_settings(smtp_host="smtp.example.com", smtp_ca_file=str(ca))

    email_service.deliver(settings, a_message(settings))

    assert seen["cafile"] == str(ca)


def test_the_default_trust_store_is_used_without_a_ca_file(settings, smtp, monkeypatch):
    real, seen = ssl.create_default_context, {}

    def spy(cafile=None):
        seen["cafile"] = cafile
        return real()

    monkeypatch.setattr(ssl, "create_default_context", spy)

    email_service.deliver(settings, a_message(settings))

    assert seen["cafile"] is None


def test_the_built_message_survives_serialization(settings):
    raw = a_message(settings).as_bytes()

    parsed = message_from_bytes(raw, policy=policy.default)

    assert parsed["Subject"] == "s"
    assert parsed["From"].addresses[0].display_name == "تبصرة"
    assert parsed["From"].addresses[0].addr_spec == "no-reply@tabsira.me"


def test_messages_come_from_the_catalog_of_the_language_and_fall_back_to_the_default():
    from src import messages

    assert messages.messages_for("ar") is messages.ARABIC
    assert messages.messages_for(None) is messages.ARABIC
    assert messages.messages_for("xx") is messages.ARABIC
    assert messages.ARABIC.direction == "rtl"
