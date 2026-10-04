"""A stand-in for Google: its signing keys, its token endpoint and ID tokens signed with them."""

from __future__ import annotations

import time
from urllib.parse import parse_qs

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from src.services import google_oidc

CLIENT_ID = "test-client-id.apps.googleusercontent.com"
NONCE = "the-nonce"
KID = "key-1"


def make_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwk_of(private_key, kid):
    public = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    return {**public, "kid": kid, "alg": "RS256", "use": "sig"}


def claims(**changes):
    now = int(time.time())
    base = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "1234567890",
        "email": "reader@example.com",
        "email_verified": True,
        "name": "Reader",
        "nonce": NONCE,
        "iat": now,
        "exp": now + 3600,
    }
    base.update(changes)
    return {key: value for key, value in base.items() if value is not None}


def sign(key, kid=KID, algorithm="RS256", **changes):
    return jwt.encode(claims(**changes), key, algorithm=algorithm, headers={"kid": kid})


class Google:
    """A fake Google: a key set that can be changed, and a count of the calls it received."""

    def __init__(self):
        self.key = make_key()
        self.keys = [jwk_of(self.key, KID)]
        self.jwks_calls = 0
        self.token_calls = []
        self.jwks_status = 200
        self.jwks_body = None
        self.token_response = httpx.Response(200, json={"id_token": "the-id-token"})
        self.raise_on = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.raise_on == str(request.url):
            message = "no route to host"
            raise httpx.ConnectError(message)
        if str(request.url) == google_oidc.JWKS_URI:
            self.jwks_calls += 1
            if self.jwks_body is not None:
                return httpx.Response(self.jwks_status, content=self.jwks_body)
            return httpx.Response(self.jwks_status, json={"keys": self.keys})
        assert str(request.url) == google_oidc.TOKEN_ENDPOINT
        self.token_calls.append(parse_qs(request.content.decode()))
        return self.token_response
