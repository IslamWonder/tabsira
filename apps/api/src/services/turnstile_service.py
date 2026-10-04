"""
Cloudflare Turnstile verification (decision 56).

A bot check is not a security control: anyone determined can solve or farm out one
challenge. What it buys is economics, since sign-up floods, credential stuffing and
mail-bombing through a reset form are only cheap when automated. It runs in front of the
rate limiter and does not replace it: the limiter bounds one attacker, this raises the cost
of being a thousand of them.

Everything fails closed. A missing token, a refused one, a timeout, a network error or an
answer that is not what Cloudflare documents all mean "not verified". Neither the token nor
the visitor's address is ever logged; only the error codes Cloudflare returns are.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from src.config import Settings

log = logging.getLogger("tabsira.turnstile")

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
# A header rather than a body field, so no request schema grows a captcha attribute and the
# generated web client does not change. S105 reads the name as a password; it is a header.
TOKEN_HEADER = "CF-Turnstile-Response"  # noqa: S105  # nosec B105
# Cloudflare answers well inside a second; the forms behind it are rate limited anyway, so
# give up quickly rather than hold a request open.
VERIFY_TIMEOUT_SECONDS = 5.0

# Cloudflare documents tokens of at most 2048 characters. Anything longer, or with other
# characters, cannot be one, so it is refused here without a call (a flood of junk must not
# become outbound traffic).
MAX_TOKEN_LENGTH = 2048
TOKEN_PATTERN = re.compile(r"[0-9A-Za-z_.-]+")

_client: httpx.AsyncClient | None = None


def http_client() -> httpx.AsyncClient:
    """Return the shared client, so verification reuses a connection."""
    global _client  # noqa: PLW0603
    if _client is None:
        _client = httpx.AsyncClient(timeout=VERIFY_TIMEOUT_SECONDS)
    return _client


async def close_http_client() -> None:
    """Close the shared client on shutdown."""
    global _client  # noqa: PLW0603
    if _client is not None:
        await _client.aclose()
        _client = None


async def post_siteverify(secret: str, token: str, remote_ip: str | None) -> dict[str, Any] | None:
    """
    Post one token to Cloudflare and return its JSON object, or None when no usable answer came.

    The single place that reaches the network, so tests and the production probe share it.
    """
    payload = {"secret": secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip
    try:
        response = await http_client().post(VERIFY_URL, data=payload)
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        # The class of the failure only: some httpx messages quote the request.
        log.warning("turnstile verification did not complete (%s)", type(exc).__name__)
        return None
    return body if isinstance(body, dict) else None


async def verify(settings: Settings, token: str | None, *, remote_ip: str | None = None) -> bool:
    """
    Verify a token with Cloudflare; True when Turnstile is off.

    A deployment without keys must not refuse every sign-in because of it.
    """
    if not settings.turnstile_enabled:
        return True
    if not token or len(token) > MAX_TOKEN_LENGTH or not TOKEN_PATTERN.fullmatch(token):
        return False
    body = await post_siteverify(settings.turnstile_secret_key.get_secret_value(), token, remote_ip)
    if body is None:
        return False
    if body.get("success") is True:
        return True
    # The codes tell a forged token from a replayed one from a wrong secret.
    codes = body.get("error-codes")
    log.info("turnstile refused a token: %s", codes if isinstance(codes, list) else [])
    return False
