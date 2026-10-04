"""
The server-side half of a Google sign-in in flight.

`start` stores a random state, the PKCE verifier and a nonce, plus a hash of a
random "binder" that goes to the browser as a cookie. `consume` finds the row
by the state Google sends back, deletes it in the same statement (a state works
once) and accepts it only while unexpired and only from the browser that holds
the binder. Without the binder, an attacker could start a sign-in, then trick a
victim's browser into finishing it, and sign the victim into the attacker's account.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock, security
from src.config import Settings
from src.models.session import OAuthState

NEXT_PATH_MAX = 200
VERIFIER_BYTES = 64  # 86 URL-safe characters; RFC 7636 allows 43 to 128


@dataclass(frozen=True)
class StartedFlow:
    state: str
    binder: str
    verifier: str
    nonce: str


@dataclass(frozen=True)
class FinishedFlow:
    verifier: str
    nonce: str
    next_path: str | None
    accepted_terms_version: str | None = None
    accepted_privacy_version: str | None = None


def safe_next_path(value: str | None) -> str | None:
    """
    Return `value` when it is a path inside the web app, else None.

    The web app's address is put in front of it, so it can never name another
    site; refusing `//`, backslashes and control characters keeps it from being
    read as a scheme-relative address by anything that looks at it first.
    """
    if (
        not value
        or len(value) > NEXT_PATH_MAX
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        return None
    return value


async def start(
    db: AsyncSession,
    settings: Settings,
    next_path: str | None,
    *,
    accepted_terms_version: str | None = None,
    accepted_privacy_version: str | None = None,
) -> StartedFlow:
    """
    Store a new sign-in and return the secrets the redirect and the cookie carry.

    The versions of the terms and the privacy policy the person ticked are kept with it,
    for the callback to record if it creates an account.
    """
    now = clock.utcnow()
    await db.execute(delete(OAuthState).where(OAuthState.expires_at < now))
    flow = StartedFlow(
        state=security.new_token(),
        binder=security.new_token(),
        verifier=security.new_token_of(VERIFIER_BYTES),
        nonce=security.new_token(),
    )
    db.add(
        OAuthState(
            state_hash=security.hash_token(flow.state).hex(),
            binder_hash=security.hash_token(flow.binder).hex(),
            code_verifier=flow.verifier,
            nonce=flow.nonce,
            next_path=safe_next_path(next_path),
            accepted_terms_version=accepted_terms_version,
            accepted_privacy_version=accepted_privacy_version,
            created_at=now,
            expires_at=now + timedelta(seconds=settings.google_state_ttl_seconds),
        )
    )
    await db.flush()
    return flow


async def consume(db: AsyncSession, state: str, binder: str | None) -> FinishedFlow | None:
    """
    Spend a state and return what the callback needs, or None if it must be refused.

    The row is deleted whether or not the rest checks out, so a refused state
    cannot be retried.
    """
    row = (
        await db.execute(
            delete(OAuthState)
            .where(OAuthState.state_hash == security.hash_token(state).hex())
            .returning(OAuthState)
        )
    ).scalar_one_or_none()
    if row is None or row.expires_at <= clock.utcnow():
        return None
    if binder is None or not hmac.compare_digest(
        row.binder_hash, security.hash_token(binder).hex()
    ):
        return None
    return FinishedFlow(
        verifier=row.code_verifier,
        nonce=row.nonce,
        next_path=row.next_path,
        accepted_terms_version=row.accepted_terms_version,
        accepted_privacy_version=row.accepted_privacy_version,
    )
