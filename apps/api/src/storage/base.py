"""
Photo storage: where consented photos are kept, behind one small interface (decisions 8 and 19).

A photo is kept as one JPEG object under a key that nobody can guess:

- `private/<32 random hex digits>.jpg` is the owner's copy. It is never public: a reader gets
  a signed link that expires within minutes (`SIGNED_URL_TTL_SECONDS`).
- `public/<32 random hex digits>.jpg` is a copy made only when its owner publishes, and removed
  when they withdraw. It has a key of its own, so its address says nothing about the private one.

The 128 random bits come from `secrets`, so the key of one photo reveals nothing about another
and nothing about its owner. Every implementation checks a key against `KEY` before it touches
anything, so a key that is not of this shape cannot reach a path or an object name.

What may be kept at all is decided one level up (`src/storage/photos.py`); this module only
stores and fetches what it is given.
"""

from __future__ import annotations

import re
import secrets
from typing import Protocol

PRIVATE_PREFIX = "private"
PUBLIC_PREFIX = "public"
CONTENT_TYPE = "image/jpeg"
# Images are re-encoded to JPEG before they are kept (`src/services/image_service.py`).
KEY = re.compile(r"^(?P<prefix>private|public)/(?P<id>[0-9a-f]{32})\.jpg$")
# The longest a signed link may live, whatever a caller asks for.
MAX_SIGNED_URL_TTL_SECONDS = 3600
# The most one object may hold: a re-encoded photo is a few megabytes at most.
MAX_OBJECT_BYTES = 20 * 1024 * 1024


class StorageError(Exception):
    """Something went wrong with storage; the subclasses say what."""


class InvalidKeyError(StorageError, ValueError):
    """A key that is not of the shape this module makes, or not allowed for what was asked."""


class ObjectNotFoundError(StorageError, LookupError):
    """There is no object under that key."""


class InvalidTtlError(StorageError, ValueError):
    """A signed link asked to live for no time at all, or longer than an hour."""


class StorageUnavailableError(StorageError):
    """The storage could not be reached or refused the call: the caller should say so and go on."""


class StorageConfigError(StorageError):
    """The settings do not describe a usable storage."""


def new_key(prefix: str) -> str:
    """Return a new random key under `prefix`."""
    if prefix not in {PRIVATE_PREFIX, PUBLIC_PREFIX}:
        message = f"unknown prefix {prefix!r}"
        raise InvalidKeyError(message)
    return f"{prefix}/{secrets.token_hex(16)}.jpg"


def new_private_key() -> str:
    """Return a new key for an owner's private copy."""
    return new_key(PRIVATE_PREFIX)


def new_public_key() -> str:
    """Return a new key for a published copy."""
    return new_key(PUBLIC_PREFIX)


def split_key(key: str) -> tuple[str, str]:
    """Return the prefix and the random id of a key; raise `InvalidKeyError` when it is not one."""
    match = KEY.fullmatch(key)
    if match is None:
        message = "not a storage key"
        raise InvalidKeyError(message)
    return match["prefix"], match["id"]


def check_key(key: str) -> str:
    """Return `key` when it has the shape of a key made here; raise `InvalidKeyError` otherwise."""
    split_key(key)
    return key


def is_public_key(key: str) -> bool:
    """Whether `key` is under the public prefix. The key is checked first."""
    return split_key(key)[0] == PUBLIC_PREFIX


def check_ttl(seconds: int) -> int:
    """Return the life of a signed link in seconds when it is between 1 and an hour."""
    if not 1 <= seconds <= MAX_SIGNED_URL_TTL_SECONDS:
        message = f"a signed link lives between 1 and {MAX_SIGNED_URL_TTL_SECONDS} seconds"
        raise InvalidTtlError(message)
    return seconds


def check_object(key: str, data: bytes, content_type: str) -> None:
    """Refuse what is not a non-empty, bounded JPEG object under a valid key."""
    check_key(key)
    if content_type != CONTENT_TYPE:
        message = f"only {CONTENT_TYPE} objects are kept"
        raise InvalidKeyError(message)
    if not data or len(data) > MAX_OBJECT_BYTES:
        message = "an object must hold between 1 byte and 20 MiB"
        raise InvalidKeyError(message)


class Storage(Protocol):
    """
    Keeps photos by key. Every method but the two URL builders may wait on a disk or a network.

    `signed_url` and `public_url` only compute an address and never fail on a missing object:
    asking the address is what finds out. `public_url` refuses a private key, so no code path
    can turn a private photo into a public address.
    """

    async def put(self, key: str, data: bytes, *, content_type: str = CONTENT_TYPE) -> None:
        """Store `data` under `key`, replacing what was there."""

    async def get(self, key: str) -> bytes:
        """Return the object, or raise `ObjectNotFoundError`."""

    async def exists(self, key: str) -> bool:
        """Whether an object is stored under `key`."""

    async def delete(self, key: str) -> None:
        """Remove the object; removing one that is not there is not an error."""

    async def copy(self, source: str, destination: str) -> None:
        """Copy an object to another key, or raise `ObjectNotFoundError` when there is no source."""

    def signed_url(self, key: str, *, ttl_seconds: int | None = None) -> str:
        """Return a link that reads the object until it expires (the setting's TTL by default)."""

    def public_url(self, key: str) -> str:
        """Return the permanent address of a published copy; refuse a private key."""
