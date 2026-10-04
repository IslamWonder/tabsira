from __future__ import annotations

import logging

import pytest

from src.cli import mail_test
from src.services import email_service


@pytest.fixture
def env(monkeypatch, tmp_path):
    """The CLI reads its settings from the environment, as it does on a server."""
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "mailer")


def test_the_default_run_sends_only_the_verification_mail(env, mailbox, capsys):
    code = mail_test.main(["you@example.com"])

    out = capsys.readouterr().out
    assert code == 0
    assert [message["To"] for message in mailbox] == ["you@example.com"]
    assert mailbox[0]["Subject"] == "أكّد بريدك الإلكتروني في تبصرة"
    assert "sent    verification" in out
    assert "smtp.example.com:587 (starttls) as mailer" in out
    assert "password reset" not in out


def test_all_sends_both_mails_with_placeholder_tokens(env, mailbox, capsys):
    code = mail_test.main(["you@example.com", "--all"])

    assert code == 0
    assert len(mailbox) == 2
    body = mailbox[1].get_body(preferencelist=("plain",)).get_content()
    assert mail_test.PLACEHOLDER_TOKEN in body
    out = capsys.readouterr().out
    assert "sent    verification" in out
    assert "sent    password reset" in out


def test_a_mail_that_cannot_be_sent_exits_1_and_says_to_read_the_log(
    env, monkeypatch, capsys, caplog
):
    def refuse(_settings, _message):
        message = "530 From/Sender name is not valid"
        raise OSError(message)

    monkeypatch.setattr(email_service, "deliver", refuse)

    with caplog.at_level(logging.ERROR, logger="tabsira.email"):
        code = mail_test.main(["you@example.com", "--all"])

    out = capsys.readouterr().out
    assert code == 1
    assert out.count("failed  ") == 2
    assert "the reason is logged above" in out
    assert "530 From/Sender name is not valid" in caplog.text
    assert "you@example.com" not in caplog.text


def test_without_smtp_it_fails_and_the_log_says_why(monkeypatch, capsys, caplog):
    monkeypatch.delenv("SMTP_HOST", raising=False)

    with caplog.at_level(logging.ERROR, logger="tabsira.email"):
        code = mail_test.main(["you@example.com"])

    assert code == 1
    assert "SMTP is not configured" in caplog.text
    assert "(not set)" in capsys.readouterr().out


def test_a_broken_configuration_exits_1_naming_the_key(monkeypatch, capsys):
    monkeypatch.setenv("SMTP_SECURITY", "plain")

    code = mail_test.main(["you@example.com"])

    assert code == 1
    assert "SMTP_SECURITY" in capsys.readouterr().err
