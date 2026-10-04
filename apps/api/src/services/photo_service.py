"""
The consented photo of an insight (v2 §15 and §19, decisions 8 and 44).

Kept at «تمّ», copied for the public while a publication shows it, removed with the insight
and the account.

`src/storage/photos.py` holds the rules and `PhotoStore` applies them; this module is the one
caller that gathers the facts those rules need from the account and the scan, and that keeps
the two keys on the insight row. Nothing here reads a photo for a guest, a sensitive scene, an
account that said it is under 13 or one that did not switch photo storage on: `PhotoFacts`
refuses before the storage is asked for anything.

A photo is a secondary effect of the owner's act. When Redis or the storage cannot be reached,
the act itself («تمّ», a publication, a withdrawal) still goes through and the photo part is
logged as a warning, with the insight's id and never a key or a reason that names the person.
"""

from __future__ import annotations

import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.profile import AgeRange, Profile
from src.models.scan import Insight, Scan
from src.scans import buffer
from src.services.image_service import ImageRejectedError, process_photo_in_thread
from src.storage.base import StorageError
from src.storage.photos import PhotoFacts, PhotoStore

log = logging.getLogger("tabsira.photos")


async def facts_for(db: AsyncSession, insight: Insight, scan: Scan | None) -> PhotoFacts:
    """State what the rules need about `insight`'s owner and scene; nothing is guessed."""
    profile = (
        await db.scalar(select(Profile).where(Profile.user_id == insight.user_id))
        if insight.user_id is not None
        else None
    )
    return PhotoFacts(
        owner_id=insight.user_id,
        age_range=profile.age_range if profile is not None else AgeRange.UNKNOWN,
        sensitive_scene=scan is not None and scan.sensitive,
        photo_storage_consent=bool(profile is not None and profile.photo_storage_consent),
    )


async def keep_from_buffer(
    db: AsyncSession, redis: Redis, store: PhotoStore, insight: Insight
) -> bool:
    """
    Keep the scan's photo as the owner's private copy at «تمّ», when the rules allow it.

    The copy still in the temporary store is re-encoded once more (upright, at most 2560
    pixels on the longer side, no metadata) and written under a new private key, which the
    insight records. The buffer copy keeps its own hour. Returns whether a photo was kept;
    False, and nothing written, for a guest, an insight without a scan, a photo already kept,
    an expired buffer, a refusal of the rules, or a store that cannot be reached.
    """
    if insight.user_id is None or insight.scan_id is None or insight.photo_key is not None:
        return False
    scan = await db.get(Scan, insight.scan_id)
    facts = await facts_for(db, insight, scan)
    if scan is None or facts.refusal(store.settings) is not None:
        return False
    try:
        raw = await buffer.get(
            redis, scan.id, buffer.Copy.FULL, key=buffer.photo_key(store.settings)
        )
    except RedisError:
        log.warning("photo of insight %s not kept: the temporary store is down", insight.id)
        return False
    if raw is None:
        return False
    try:
        stored = await store.keep(facts, await process_photo_in_thread(raw))
    except (ImageRejectedError, StorageError):
        log.warning("photo of insight %s not kept: the photo store refused it", insight.id)
        return False
    insight.photo_key = stored.key
    await db.flush()
    return True


async def remove(store: PhotoStore, insight: Insight) -> None:
    """Delete both copies of the insight's photo and forget their keys; nothing when there is none."""
    if insight.photo_public_key is not None:
        await store.withdraw(insight.photo_public_key)
        insight.photo_public_key = None
    if insight.photo_key is not None:
        await store.remove(insight.photo_key)
        insight.photo_key = None
