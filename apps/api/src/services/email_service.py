"""
Transactional mail, sent by the API itself over SMTP.

Two kinds go out: the e-mail verification link and the password reset link.
Each is a plain-text and an HTML part rendered by Jinja2 from
`src/templates/email/<language>` (Arabic, right to left, today); the subjects
come from `src/messages.py` in the same language. HTML is autoescaped, so a
display name cannot inject markup. Every mail carries `Auto-Submitted:
auto-generated` so auto-responders stay quiet.

Every function fails soft. The routes that call them must answer the same
whether or not an address has an account, and must not fail because a mail
server is down, so a mail that cannot be sent is logged and reported as False,
never raised. While SMTP_HOST is empty nothing is sent and an error is logged.

Nothing here logs an address or a token: these routes are open to anyone, so
the address is whatever an attacker typed. A failure is logged by its kind and
the server's own words, with the recipient's address cut out of them.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from src import messages
from src.config import Settings

log = logging.getLogger("tabsira.email")

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"
FAILURE_TEXT_MAX = 300


@cache
def _templates(language: str) -> Environment:
    """Return the templates of one language; each language has its own folder."""
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR / language),
        # HTML is autoescaped; the plain-text parts are not HTML and must stay as written.
        autoescape=select_autoescape(enabled_extensions=("html",), default_for_string=False),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def build_message(
    settings: Settings,
    *,
    to: str,
    subject: str,
    template: str,
    context: dict[str, Any],
    language: str | None = None,
) -> EmailMessage:
    """Render a template into a message: text part first, HTML as the alternative."""
    catalog = messages.messages_for(language)
    sender_domain = parseaddr(settings.mail_from)[1].rpartition("@")[2] or None
    page = {
        **context,
        "site_name": catalog.site_name,
        "support_email": settings.mail_reply_to,
    }
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.mail_from
    message["To"] = to
    if settings.mail_reply_to:
        message["Reply-To"] = settings.mail_reply_to
    message["Date"] = formatdate(localtime=False, usegmt=True)
    message["Message-ID"] = make_msgid(domain=sender_domain)
    # Tells servers and clients this is machine-sent: no auto-replies, no vacation
    # responder answering a password reset.
    message["Auto-Submitted"] = "auto-generated"
    templates = _templates(catalog.language)
    message.set_content(templates.get_template(f"{template}.txt").render(page))
    message.add_alternative(templates.get_template(f"{template}.html").render(page), subtype="html")
    return message


def deliver(settings: Settings, message: EmailMessage) -> None:
    """
    Talk to the SMTP server. Blocking: run it in a worker thread.

    Always encrypted: implicit TLS for `ssl`, STARTTLS for `starttls`, and a
    server that does not offer STARTTLS is an error, not a fallback to clear text.
    """
    context = ssl.create_default_context(cafile=settings.smtp_ca_file or None)
    timeout = settings.smtp_timeout_seconds
    if settings.smtp_security == "ssl":
        server: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=timeout, context=context
        )
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout)
        try:
            server.starttls(context=context)
        except BaseException:
            server.close()
            raise
    with server:
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        server.send_message(message)


def describe_failure(error: BaseException, recipient: str) -> str:
    """Return what went wrong, short, without the recipient's address."""
    text = f"{type(error).__name__}: {error}".replace(recipient, "<recipient>")
    return text[:FAILURE_TEXT_MAX]


async def send(
    settings: Settings,
    *,
    to: str,
    subject: str,
    template: str,
    context: dict[str, Any],
    purpose: str,
) -> bool:
    """Render and send one message. Returns False, after logging why, instead of raising."""
    if not settings.smtp_configured:
        log.error("Cannot send %s: SMTP is not configured (SMTP_HOST, MAIL_FROM)", purpose)
        return False
    try:
        message = build_message(
            settings, to=to, subject=subject, template=template, context=context
        )
        await asyncio.to_thread(deliver, settings, message)
    except Exception as error:
        log.error("Failed to send %s: %s", purpose, describe_failure(error, to))  # noqa: TRY400
        return False
    log.info("Sent %s", purpose)
    return True


def link(settings: Settings, path: str, token: str) -> str:
    """
    Build the link a mail carries: the web app's page, with the token in the fragment.

    A fragment is never sent to a server, so the token stays out of the web
    server's access log and of any Referer header; the page reads it from the
    address bar and posts it to the API.
    """
    return f"{settings.mail_link_base}{path}#token={quote(token, safe='')}"


async def send_email_verification(settings: Settings, *, email: str, name: str, token: str) -> bool:
    """Send the link that confirms an address belongs to its account."""
    return await send(
        settings,
        to=email,
        subject=messages.messages_for().verify_email_subject,
        template="verify_email",
        context={
            "name": name,
            "verify_url": link(settings, "/verify-email", token),
            "expires_hours": settings.email_verification_expire_hours,
        },
        purpose="email verification",
    )


async def send_password_reset(settings: Settings, *, email: str, name: str, token: str) -> bool:
    """Send the link that lets the owner of an address choose a new password."""
    return await send(
        settings,
        to=email,
        subject=messages.messages_for().reset_password_subject,
        template="password_reset",
        context={
            "name": name,
            "reset_url": link(settings, "/reset-password", token),
            "expires_minutes": settings.password_reset_expire_minutes,
        },
        purpose="password reset",
    )


def build_support_message(
    settings: Settings,
    *,
    reply_to: str,
    topic: str,
    name: str | None,
    text: str,
    account_id: str | None,
    account_match: bool | None = None,
    language: str | None = None,
) -> EmailMessage:
    """
    Build the mail the support form sends to SUPPORT_EMAIL, replies going to the visitor.

    Plain text only. Nothing about the visitor's connection goes in (no IP, no user agent).
    The account id, when they were signed in, is in the `X-Tabsira-Account` header, which
    the visitor cannot write to. The body starts with one header-like line saying whether
    the typed address is the signed-in account's verified one; then, after a separator, the
    visitor's message with every line quoted by "> ", so nothing they type can pass for the
    lines above it, the account line included.
    """
    catalog = messages.messages_for(language)
    label = catalog.support_topics[topic]
    if account_match is None:
        match = catalog.support_match_guest
    else:
        match = catalog.support_match_yes if account_match else catalog.support_match_no
    lines = [
        f"{catalog.support_label_match}: {match}",
        f"{catalog.support_label_topic}: {label}",
        f"{catalog.support_label_name}: {name or '-'}",
        f"{catalog.support_label_email}: {reply_to}",
    ]
    lines += ["-" * 20, *(f"> {line}" for line in text.splitlines())]
    sender_domain = parseaddr(settings.mail_from)[1].rpartition("@")[2] or None
    message = EmailMessage()
    message["Subject"] = catalog.support_subject.format(topic=label)
    message["From"] = settings.mail_from
    message["To"] = settings.support_email
    message["Reply-To"] = reply_to
    message["Date"] = formatdate(localtime=False, usegmt=True)
    message["Message-ID"] = make_msgid(domain=sender_domain)
    # Keeps auto-responders and vacation replies from answering the team's mailbox.
    message["Auto-Submitted"] = "auto-generated"
    message["X-Auto-Response-Suppress"] = "All"
    if account_id is not None:
        message["X-Tabsira-Account"] = account_id
    message.set_content("\n".join(lines))
    return message


async def send_support_message(
    settings: Settings,
    *,
    reply_to: str,
    topic: str,
    name: str | None,
    text: str,
    account_id: str | None,
    account_match: bool | None = None,
) -> bool:
    """
    Send one support message now. Returns False, never raising, when it cannot go.

    Nothing of the message or of the visitor's address is logged: only that a send failed
    and the kind of error.
    """
    if not settings.smtp_configured:
        log.error("Cannot send a support message: SMTP is not configured (SMTP_HOST, MAIL_FROM)")
        return False
    try:
        message = build_support_message(
            settings,
            reply_to=reply_to,
            topic=topic,
            name=name,
            text=text,
            account_id=account_id,
            account_match=account_match,
        )
        await asyncio.to_thread(deliver, settings, message)
    except Exception as error:
        log.error("Failed to send a support message: %s", type(error).__name__)  # noqa: TRY400
        return False
    return True
