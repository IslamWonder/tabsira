"""
Passwords, session tokens and keyed hashes.

Three rules hold everywhere here. A secret is compared in constant time or by
its hash. A password is hashed with bcrypt only. An IP address or an e-mail
address that must be remembered (to rate limit) is stored as an HMAC under a
server key, never as itself: the address space is small enough that a plain
hash of an IPv4 address can be reversed in minutes.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
from functools import lru_cache

import bcrypt

MIN_PASSWORD_LENGTH = 10
# bcrypt reads at most 72 bytes; version 5 refuses more instead of cutting them.
MAX_PASSWORD_BYTES = 72
# What the cookie carries: 256 random bits, URL-safe.
TOKEN_BYTES = 32
UNKNOWN_IP = "unknown"


def new_token_of(size: int) -> str:
    """Return `size` random bytes as URL-safe text."""
    return secrets.token_urlsafe(size)


def new_token() -> str:
    """Return a fresh random token: 256 bits as URL-safe text."""
    return new_token_of(TOKEN_BYTES)


def hash_token(token: str) -> bytes:
    """
    Return the SHA-256 digest under which a token is stored.

    A plain hash is enough: the token is 256 random bits, so there is nothing to
    guess and no reason to slow the lookup that runs on every request.
    """
    return hashlib.sha256(token.encode()).digest()


def keyed_hash(key: bytes, purpose: str, value: str) -> str:
    """Return the HMAC-SHA256 of `value`, as hex; `purpose` keeps the uses apart."""
    return hmac.new(key, f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def normalize_client_ip(host: str | None) -> str:
    """
    Return the address a rate limit should count.

    An IPv6 address is cut to its /64: one subscriber holds a whole /64, so
    counting full addresses would let a single machine rotate through billions.
    """
    if not host:
        return UNKNOWN_IP
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


def password_problem(password: str) -> str | None:
    """Return why `password` cannot be used, or None when it can."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"must have at least {MIN_PASSWORD_LENGTH} characters"
    if "\x00" in password:
        return "must not contain a null character"
    if len(password.encode()) > MAX_PASSWORD_BYTES:
        return f"must be at most {MAX_PASSWORD_BYTES} bytes long (Arabic letters take two)"
    return None


def hash_password(password: str, rounds: int) -> str:
    """Return the bcrypt hash of a password that passed `password_problem`. Blocking: run it in a thread."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=rounds)).decode()


@lru_cache(maxsize=8)
def _decoy_hash(rounds: int) -> str:
    """Return a hash of nothing real, checked when no account exists so that both cases take as long."""
    return hash_password("decoy-password-never-valid", rounds)


def verify_password(password: str, password_hash: str | None, rounds: int) -> bool:
    """
    Check a password against a stored hash, in constant time.

    With no hash (no such account, or one that signs in with Google only) it
    still pays for a full bcrypt check against a decoy, so the answer's timing
    does not tell whether the address is registered. Blocking: run it in a thread.
    """
    if password_hash is None:
        _verify(password, _decoy_hash(rounds))
        return False
    return _verify(password, password_hash)


def _verify(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        # Too long for bcrypt, or a stored hash that is not one: neither matches.
        return False
