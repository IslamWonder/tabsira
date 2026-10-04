"""
The temporary store of a scan's photo (v2 §19: «مخزن مؤقت يُمسح تلقائيًا»).

Only the stripped copies made by the image validator are kept, never the
upload: the full copy, which its owner may see again while the scan is fresh,
and the model copy the job sends to the detector and the vision model. Both
expire after SCAN_IMAGE_TTL_SECONDS without anyone deleting them; the model
copy is deleted when the job no longer needs it, and both are deleted at once
when the scene turns out to be sensitive (rule 8).
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import cast

from redis.asyncio import Redis

from src.pipeline.schemas import EncodedImage


class Copy(StrEnum):
    FULL = "image"
    MODEL = "model_image"


def _key(scan_id: uuid.UUID, copy: Copy) -> str:
    return f"scan:{scan_id}:{copy.value}"


async def put(
    redis: Redis, scan_id: uuid.UUID, *, full: EncodedImage, model: EncodedImage, ttl: int
) -> None:
    """Keep both copies of a new scan's photo for `ttl` seconds."""
    async with redis.pipeline(transaction=True) as pipe:
        pipe.set(_key(scan_id, Copy.FULL), full.data, ex=ttl)
        pipe.set(_key(scan_id, Copy.MODEL), model.data, ex=ttl)
        await pipe.execute()


async def get(redis: Redis, scan_id: uuid.UUID, copy: Copy) -> bytes | None:
    """Return a copy while it lives, else None."""
    return cast("bytes | None", await redis.get(_key(scan_id, copy)))


async def drop(redis: Redis, scan_id: uuid.UUID, *copies: Copy) -> None:
    """Delete the given copies now (every copy when none is named)."""
    chosen = copies or tuple(Copy)
    await redis.delete(*(_key(scan_id, copy) for copy in chosen))
