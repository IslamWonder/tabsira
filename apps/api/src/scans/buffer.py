"""
The temporary store of a scan's photo (v2 §19: «مخزن مؤقت يُمسح تلقائيًا»).

Only the stripped copies made by the image validator are kept, never the
upload: the full copy, which its owner may see again while the scan is fresh,
and the model copy the job sends to the detector and the vision model. Both
expire after SCAN_IMAGE_TTL_SECONDS without anyone deleting them; the model
copy is deleted when the job no longer needs it, and both are deleted at once
when the scene turns out to be sensitive (rule 8).

Redis may write what it holds to disk (its snapshots and append-only file), so
a photo is never given to it in clear: each copy is sealed with AES-GCM under a
key derived from HASH_SECRET, which Redis never sees, and bound to its scan and
copy so one sealed value cannot stand in for another. What reaches a Redis
disk is ciphertext that outlives nothing: the key is not on that host.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from enum import StrEnum
from typing import cast

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from redis.asyncio import Redis

from src.config import Settings
from src.pipeline.schemas import EncodedImage

NONCE_BYTES = 12
KEY_PURPOSE = b"tabsira-scan-photo-buffer-v1"


class Copy(StrEnum):
    FULL = "image"
    MODEL = "model_image"


def photo_key(settings: Settings) -> bytes:
    """Return the 256-bit key that seals photos in Redis, derived from the server key."""
    return hmac.new(settings.hash_key, KEY_PURPOSE, hashlib.sha256).digest()


def _key(scan_id: int, copy: Copy) -> str:
    return f"scan:{scan_id}:{copy.value}"


def _seal(key: bytes, scan_id: int, copy: Copy, data: bytes) -> bytes:
    nonce = os.urandom(NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, data, _key(scan_id, copy).encode())


def _open(key: bytes, scan_id: int, copy: Copy, sealed: bytes) -> bytes | None:
    nonce, ciphertext = sealed[:NONCE_BYTES], sealed[NONCE_BYTES:]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, _key(scan_id, copy).encode())
    except InvalidTag:
        return None


async def put(
    redis: Redis,
    scan_id: int,
    *,
    full: EncodedImage,
    model: EncodedImage,
    ttl: int,
    key: bytes,
) -> None:
    """Keep both copies of a new scan's photo, sealed, for `ttl` seconds."""
    async with redis.pipeline(transaction=True) as pipe:
        pipe.set(_key(scan_id, Copy.FULL), _seal(key, scan_id, Copy.FULL, full.data), ex=ttl)
        pipe.set(_key(scan_id, Copy.MODEL), _seal(key, scan_id, Copy.MODEL, model.data), ex=ttl)
        await pipe.execute()


async def get(redis: Redis, scan_id: int, copy: Copy, *, key: bytes) -> bytes | None:
    """Return a copy while it lives and its seal holds, else None."""
    sealed = cast("bytes | None", await redis.get(_key(scan_id, copy)))
    return None if sealed is None else _open(key, scan_id, copy, sealed)


async def kept(redis: Redis, scan_id: int, copy: Copy) -> bool:
    """Tell whether a copy is still in the store."""
    return bool(await redis.exists(_key(scan_id, copy)))


async def drop(redis: Redis, scan_id: int, *copies: Copy) -> None:
    """Delete the given copies now (every copy when none is named)."""
    chosen = copies or tuple(Copy)
    await redis.delete(*(_key(scan_id, copy) for copy in chosen))
