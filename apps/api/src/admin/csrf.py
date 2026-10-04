"""
CSRF tokens of the admin area.

Two kinds, because there are two situations:

- Signed in: the token is `admin_session_service.csrf_token_for`, a keyed hash of the
  session cookie. Every state-changing admin request (POST, PUT, PATCH, DELETE) must carry
  it, in the `X-CSRF-Token` header or the `csrf_token` form field. The templates put it
  in every form and in a meta tag the admin script reads for requests it makes itself.
- Signing in: there is no session yet, so the sign-in form carries a keyed hash of a
  random nonce that the same response set as a cookie. A page of another site can make the
  browser send the cookie but cannot compute the hash, which needs the server's key.

The template reads the current token through `csrf_token()`; it is held in a context
variable that the admin sets for the duration of one request.
"""

from __future__ import annotations

import hmac
from contextvars import ContextVar, Token

from starlette.requests import Request
from starlette.responses import Response

from src import security
from src.config import Settings

CSRF_HEADER = "X-CSRF-Token"
CSRF_FIELD = "csrf_token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

LOGIN_COOKIE_NAME = "__Secure-tabsira_admin_login"
# The sign-in form is open for ten minutes after it is served.
LOGIN_FORM_SECONDS = 600
LOGIN_PURPOSE = "admin-login-csrf"
NONCE_MAX = 128

_current: ContextVar[str] = ContextVar("admin_csrf_token", default="")


def csrf_token() -> str:
    """Return the token of the request being served, for templates; empty outside one."""
    return _current.get()


def use_token(token: str) -> None:
    """Make `token` the one templates see for the rest of this request."""
    _current.set(token)


def forget_token() -> Token[str]:
    """Clear the token for a new request and return what restores the previous state."""
    return _current.set("")


def restore(marker: Token[str]) -> None:
    """Undo `forget_token`, so one request's token never outlives it."""
    _current.reset(marker)


def tokens_match(expected: str, received: str | None) -> bool:
    """Compare two tokens in constant time; a missing one never matches."""
    return bool(expected) and bool(received) and hmac.compare_digest(expected, received or "")


async def submitted_token(request: Request) -> str | None:
    """Return the token a request carries: its header first, else its form field."""
    header = request.headers.get(CSRF_HEADER)
    if header:
        return header
    field = (await request.form()).get(CSRF_FIELD)
    return field if isinstance(field, str) else None


def login_form_token(settings: Settings, nonce: str) -> str:
    """Return the value the sign-in form must send back for the cookie holding `nonce`."""
    return security.keyed_hash(settings.hash_key, LOGIN_PURPOSE, nonce)


def new_login_nonce() -> str:
    return security.new_token()


def set_login_cookie(response: Response, nonce: str) -> None:
    """Attach the nonce of the sign-in form: httpOnly, Secure, SameSite=Strict, path /admin."""
    response.set_cookie(
        LOGIN_COOKIE_NAME,
        nonce,
        max_age=LOGIN_FORM_SECONDS,
        path="/admin",
        secure=True,
        httponly=True,
        samesite="strict",
    )


def clear_login_cookie(response: Response) -> None:
    response.delete_cookie(
        LOGIN_COOKIE_NAME, path="/admin", secure=True, httponly=True, samesite="strict"
    )


def login_form_valid(settings: Settings, request: Request, submitted: str | None) -> bool:
    """Whether the submitted sign-in token is the one for the nonce in the request's cookie."""
    nonce = request.cookies.get(LOGIN_COOKIE_NAME)
    if not nonce or len(nonce) > NONCE_MAX:
        return False
    return tokens_match(login_form_token(settings, nonce), submitted)
