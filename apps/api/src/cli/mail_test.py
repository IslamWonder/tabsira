"""
Send a test mail through the configured SMTP server.

    uv run python -m src.cli.mail_test you@example.com          # the verification mail
    uv run python -m src.cli.mail_test you@example.com --all    # both mails

It proves the SMTP_* and MAIL_FROM settings end to end before a real user
depends on them: the connection, TLS, the login, and the mail server accepting
the sender's domain. The links carry a placeholder token, so following one
shows the invalid-link page. Exits 1 when a mail could not be sent, with the
server's reason logged above, the recipient's address cut out of it.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable, Sequence

from src.config import ConfigError, Settings, load_settings
from src.services import email_service

PLACEHOLDER_TOKEN = "mail-test-placeholder-not-a-real-token"  # noqa: S105  # nosec B105
TEST_NAME = "تبصرة (اختبار)"

Mail = tuple[str, Callable[[], Awaitable[bool]]]


def mails(settings: Settings, to: str) -> list[Mail]:
    """Return the mails this tool can send, each with its label."""
    return [
        (
            "verification",
            lambda: email_service.send_email_verification(
                settings, email=to, name=TEST_NAME, token=PLACEHOLDER_TOKEN
            ),
        ),
        (
            "password reset",
            lambda: email_service.send_password_reset(
                settings, email=to, name=TEST_NAME, token=PLACEHOLDER_TOKEN
            ),
        ),
    ]


async def run(settings: Settings, to: str, *, send_all: bool) -> int:
    """Send the chosen mails and return the exit code."""
    chosen = mails(settings, to)
    if not send_all:
        chosen = chosen[:1]
    sys.stdout.write(
        f"SMTP {settings.smtp_host or '(not set)'}:{settings.smtp_port} ({settings.smtp_security}) "
        f"as {settings.smtp_username or '(no login)'}, from {settings.mail_from}\n"
    )
    failed = 0
    for label, send in chosen:
        if await send():
            sys.stdout.write(f"sent    {label}\n")
        else:
            failed += 1
            sys.stdout.write(f"failed  {label}: the reason is logged above\n")
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Send the test mail; return the process exit code."""
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.mail_test",
        description="Send a test mail through the SMTP settings.",
    )
    parser.add_argument("to", help="address to send the test mail to")
    parser.add_argument("--all", action="store_true", help="send both transactional mails")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    try:
        settings = load_settings()
    except ConfigError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    return asyncio.run(run(settings, args.to, send_all=args.all))


if __name__ == "__main__":
    raise SystemExit(main())
