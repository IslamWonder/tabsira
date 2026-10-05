"""
Photo storage: where consented photos are kept, behind one small interface (decisions 8 and 19).

A photo is kept as one JPEG object under a key that nobody can guess:

- `private/users/<account id>/insights/<32 random hex digits>.jpg` is the owner's copy, under
  the owner's own folder, so everything one person kept can be listed, exported or deleted
  together (`owner_prefix`). It is never public: a reader gets a signed link that expires
  within minutes (`SIGNED_URL_TTL_SECONDS`). Copies kept before this layout are
  `private/<32 hex>.jpg` and stay readable; the storage probe still writes that shape.
- `public/<32 random hex digits>.jpg` is a copy made only when its owner publishes, and removed
  when they withdraw. It never names its owner: anyone can read its address, which must not
  expose the account id or tie one person's published photos together, nor say anything about
  the private copy. The database knows which insight each one belongs to.

The 128 random bits come from `secrets`, so the key of one photo reveals nothing about another. Every implementation checks a key against `KEY` before it touches
anything, so a key that is not of this shape cannot reach a path or an object name.

What may be kept at all is decided one level up (`src/storage/photos.py`); this module only
stores and fetches what it is given.
"""

from __future__ import annotations

import re
import secrets
import uuid
from typing import Protocol

PRIVATE_PREFIX = "private"
PUBLIC_PREFIX = "public"
CONTENT_TYPE = "image/jpeg"
# Images are re-encoded to JPEG before they are kept (`src/services/image_service.py`).
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
KEY = re.compile(
    rf"^(?P<prefix>private|public)/(?:users/(?P<owner>{_UUID})/insights/)?(?P<id>[0-9a-f]{{32}})\.jpg$"
)
OWNER_PREFIX = re.compile(rf"^private/users/{_UUID}/$")
# A mock member's photo is the address of a placeholder image (decision 66), shown as is: it
# is not an object of ours, so `KEY` refuses it and nothing here ever stores, copies, signs or
# deletes it. Strict on purpose: https, that host, `/id/<n>/<w>/<h>` with ASCII digits, nothing
# else (no query, no port, no user, no extra path), and short enough for the 64-character column.
MOCK_PHOTO_HOST = "placepix.net"
MOCK_PHOTO_ADDRESS = re.compile(r"https://placepix\.net/id/[0-9]+/[0-9]+/[0-9]+")
MOCK_PHOTO_MAX_LENGTH = 64
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


def new_private_key(owner_id: uuid.UUID | None = None) -> str:
    """Return a new key for an owner's private copy, in their folder; without one, the probe's shape."""
    if owner_id is None:
        return new_key(PRIVATE_PREFIX)
    return f"{owner_prefix(owner_id)}insights/{secrets.token_hex(16)}.jpg"


def owner_prefix(owner_id: uuid.UUID) -> str:
    """Return the folder that holds every private copy of one account, ending in a slash."""
    return f"{PRIVATE_PREFIX}/users/{owner_id}/"


def new_public_key() -> str:
    """Return a new key for a published copy."""
    return new_key(PUBLIC_PREFIX)


def split_key(key: str) -> tuple[str, str]:
    """Return the prefix and the random id of a key; raise `InvalidKeyError` when it is not one."""
    match = KEY.fullmatch(key)
    # A published copy never names its owner.
    if match is None or (match["prefix"] == PUBLIC_PREFIX and match["owner"] is not None):
        message = "not a storage key"
        raise InvalidKeyError(message)
    return match["prefix"], match["id"]


def in_owner_folder(key: str) -> bool:
    """Whether `key` is a private copy kept in its owner's folder. The key is checked first."""
    split_key(key)
    match = KEY.fullmatch(key)
    return match is not None and match["owner"] is not None


def check_owner_prefix(prefix: str) -> str:
    """Return `prefix` when it is one account's private folder; raise `InvalidKeyError` otherwise."""
    if OWNER_PREFIX.fullmatch(prefix) is None:
        message = "not an account's folder"
        raise InvalidKeyError(message)
    return prefix


def check_key(key: str) -> str:
    """Return `key` when it has the shape of a key made here; raise `InvalidKeyError` otherwise."""
    split_key(key)
    return key


def is_public_key(key: str) -> bool:
    """Whether `key` is under the public prefix. The key is checked first."""
    return split_key(key)[0] == PUBLIC_PREFIX


def is_mock_photo_address(value: str | None) -> bool:
    """Whether `value` is a placeholder photo address that is shown as is and never stored."""
    return (
        value is not None
        and len(value) <= MOCK_PHOTO_MAX_LENGTH
        and MOCK_PHOTO_ADDRESS.fullmatch(value) is not None
    )


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

    async def delete_prefix(self, prefix: str) -> int:
        """Remove every object in one account's folder (`owner_prefix`); return how many."""

    def signed_url(self, key: str, *, ttl_seconds: int | None = None) -> str:
        """Return a link that reads the object until it expires (the setting's TTL by default)."""

    def public_url(self, key: str) -> str:
        """Return the permanent address of a published copy; refuse a private key."""
