"""
Sign in with Google: OpenID Connect, authorization code flow with PKCE.

The browser is sent to Google with a state, a nonce and the SHA-256 challenge
of a code verifier that stays on our server. Google sends it back with a code;
we exchange the code, with the verifier and our client secret, for an ID token,
and accept the token only after checking its signature against Google's
published keys, its issuer, its audience, its expiry and the nonce.

Google's endpoints are fixed constants, not discovered at run time: they are
Google's published, stable ones, and a discovery call would be one more network
dependency on every sign-in. Nothing here logs a code, a token or a verifier.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt

from src import clock
from src.config import Settings

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105 - a URL, not a password  # nosec B105
JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
SCOPE = "openid email profile"
SIGNING_ALGORITHM = "RS256"
REQUIRED_CLAIMS = ["exp", "iat", "iss", "aud", "sub"]

HTTP_TIMEOUT_SECONDS = 5.0
# Seconds of clock difference with Google that an ID token's times may show.
LEEWAY_SECONDS = 60
# How long Google's keys are trusted without asking again.
JWKS_TTL_SECONDS = 3600.0
# A token naming a key we do not have makes us ask Google again, but not more
# often than this: a forged `kid` must not turn into a request per attempt.
JWKS_MIN_REFETCH_SECONDS = 60.0


class OidcError(Exception):
    """The sign-in cannot be trusted or completed. The text is for logs and holds no secret."""


@dataclass(frozen=True)
class GoogleIdentity:
    """What Google vouched for about the person, from a verified ID token."""

    subject: str
    email: str
    name: str | None


def pkce_challenge(verifier: str) -> str:
    """Return the S256 code challenge of a verifier (RFC 7636): base64url of its SHA-256."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def authorization_url(settings: Settings, *, state: str, nonce: str, verifier: str) -> str:
    """Build the address of Google's consent page for one sign-in."""
    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "state": state,
            "nonce": nonce,
            "code_challenge": pkce_challenge(verifier),
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )
    return f"{AUTHORIZATION_ENDPOINT}?{query}"


class GoogleOidc:
    """
    The two calls to Google and the validation of what comes back.

    One instance per process, so the key cache is shared. `transport` lets a
    test answer the calls without a network.
    """

    def __init__(
        self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at: float | None = None
        self._lock = asyncio.Lock()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS, transport=self._transport)

    async def exchange_code(self, code: str, verifier: str) -> str:
        """Trade the authorization code for the ID token; the access token is never used."""
        try:
            async with self._client() as client:
                response = await client.post(
                    TOKEN_ENDPOINT,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": self._settings.google_redirect_uri,
                        "client_id": self._settings.google_client_id,
                        "client_secret": self._settings.google_client_secret.get_secret_value(),
                        "code_verifier": verifier,
                    },
                )
        except httpx.HTTPError as error:
            message = f"token endpoint unreachable ({type(error).__name__})"
            raise OidcError(message) from None
        if response.status_code != httpx.codes.OK:
            message = f"token endpoint answered {response.status_code}"
            raise OidcError(message)
        try:
            id_token = response.json().get("id_token")
        except (ValueError, AttributeError):
            id_token = None
        if not isinstance(id_token, str) or not id_token:
            message = "token endpoint sent no ID token"
            raise OidcError(message)
        return id_token

    async def _fetch_keys(self) -> None:
        try:
            async with self._client() as client:
                response = await client.get(JWKS_URI)
            response.raise_for_status()
            listed = list(response.json()["keys"])
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            message = f"signing keys unavailable ({type(error).__name__})"
            raise OidcError(message) from None
        keys: dict[str, jwt.PyJWK] = {}
        for entry in listed:
            try:
                key = jwt.PyJWK.from_dict(entry)
            except (jwt.PyJWTError, TypeError, ValueError, KeyError):
                continue
            if key.key_id and key.key_type == "RSA":
                keys[key.key_id] = key
        self._keys = keys
        self._fetched_at = clock.monotonic()

    async def _signing_key(self, key_id: str) -> jwt.PyJWK:
        async with self._lock:
            age = None if self._fetched_at is None else clock.monotonic() - self._fetched_at
            if (
                age is None
                or age >= JWKS_TTL_SECONDS
                or (key_id not in self._keys and age >= JWKS_MIN_REFETCH_SECONDS)
            ):
                await self._fetch_keys()
            key = self._keys.get(key_id)
        if key is None:
            message = "the ID token names an unknown signing key"
            raise OidcError(message)
        return key

    async def verify_id_token(self, id_token: str, *, nonce: str) -> GoogleIdentity:
        """Check an ID token completely and return who it vouches for."""
        try:
            header = jwt.get_unverified_header(id_token)
        except jwt.PyJWTError:
            message = "the ID token is malformed"
            raise OidcError(message) from None
        key_id = header.get("kid")
        if header.get("alg") != SIGNING_ALGORITHM or not isinstance(key_id, str):
            message = "the ID token is not signed the way Google signs them"
            raise OidcError(message)
        key = await self._signing_key(key_id)
        try:
            claims = jwt.decode(
                id_token,
                key.key,
                algorithms=[SIGNING_ALGORITHM],
                audience=self._settings.google_client_id,
                issuer=list(ISSUERS),
                leeway=LEEWAY_SECONDS,
                options={"require": REQUIRED_CLAIMS},
            )
        except jwt.PyJWTError as error:
            message = f"the ID token was refused ({type(error).__name__})"
            raise OidcError(message) from None
        return self._identity(claims, nonce)

    @staticmethod
    def _identity(claims: dict[str, object], nonce: str) -> GoogleIdentity:
        sent_nonce = claims.get("nonce")
        if not isinstance(sent_nonce, str) or not hmac.compare_digest(
            sent_nonce.encode(), nonce.encode()
        ):
            message = "the ID token's nonce does not match"
            raise OidcError(message)
        subject, email, name = claims.get("sub"), claims.get("email"), claims.get("name")
        if not isinstance(subject, str) or not subject or not isinstance(email, str) or not email:
            message = "the ID token carries no subject or e-mail address"
            raise OidcError(message)
        # An address Google has not verified proves nothing about who owns it.
        if claims.get("email_verified") not in {True, "true"}:
            message = "Google has not verified the e-mail address"
            raise OidcError(message)
        return GoogleIdentity(
            subject=subject, email=email, name=name if isinstance(name, str) else None
        )
