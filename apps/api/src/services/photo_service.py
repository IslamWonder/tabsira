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
import uuid

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import Select, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.atlas import MapEntry, MapEntryStatus
from src.models.profile import AgeRange, Profile
from src.models.scan import Insight, Scan
from src.models.social import InsightPublication, Post, PostStatus, PostVisibility
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


def _shown_by_a_live_publication(insight_id: int) -> Select[tuple[bool]]:
    """Whether a public post or a published map entry shows the photo of the insight right now."""
    # A post for followers only is not public: the `public/` prefix is readable by anyone who
    # has the address, so only a public post or a map entry makes a public copy.
    post_shows = exists().where(
        Post.publication_id == InsightPublication.id,
        Post.status == PostStatus.PUBLISHED,
        Post.visibility == PostVisibility.PUBLIC,
        InsightPublication.insight_id == insight_id,
        InsightPublication.photo_ref.is_not(None),
    )
    entry_shows = exists().where(
        MapEntry.insight_id == insight_id,
        MapEntry.status == MapEntryStatus.PUBLISHED,
        MapEntry.with_photo.is_(True),
    )
    return select(or_(post_shows, entry_shows))


async def sync_public_copy(db: AsyncSession, store: PhotoStore, insight_id: int | None) -> None:
    """
    Make the one public copy exist exactly while a live publication shows the photo.

    Called after a post or a map entry is published, withdrawn or removed. The copy is made
    only when a published post or entry of the insight asked for the photo and the rules still
    allow it at this moment; otherwise an existing copy is deleted, so a consent withdrawn or
    an age declared since takes the photo down with the next change of state.
    """
    if insight_id is None:
        return
    insight = await db.get(Insight, insight_id)
    if insight is None or insight.photo_key is None:
        return
    scan = await db.get(Scan, insight.scan_id) if insight.scan_id is not None else None
    facts = await facts_for(db, insight, scan)
    wanted = (
        bool(await db.scalar(_shown_by_a_live_publication(insight.id)))
        and facts.refusal(store.settings) is None
    )
    try:
        if wanted and insight.photo_public_key is None:
            insight.photo_public_key = (await store.publish(facts, insight.photo_key)).key
        elif not wanted and insight.photo_public_key is not None:
            await store.withdraw(insight.photo_public_key)
            insight.photo_public_key = None
    except StorageError:
        log.warning("public copy of insight %s not updated: the photo store failed", insight.id)
        return
    await db.flush()


def public_url(store: PhotoStore, public_key: str | None) -> str | None:
    """
    Return the address anyone can read the public copy at, or None when there is no copy.

    Built from the store alone (`S3_PUBLIC_BASE_URL`, or the API's own `/media` route for the
    local disk): the address names the public key, which says nothing about the private one.
    """
    return None if public_key is None else store.storage.public_url(public_key)


async def public_urls(db: AsyncSession, store: PhotoStore, insight_ids: set[int]) -> dict[int, str]:
    """Return the public copies' addresses of the insights that have one, by insight id, in one query."""
    if not insight_ids:
        return {}
    rows = await db.execute(
        select(Insight.id, Insight.photo_public_key).where(
            Insight.id.in_(insight_ids), Insight.photo_public_key.is_not(None)
        )
    )
    return {
        insight_id: url
        for insight_id, key in rows.all()
        if (url := public_url(store, key)) is not None
    }


async def remove_all(db: AsyncSession, store: PhotoStore, user_id: uuid.UUID) -> int:
    """
    Delete both copies of every photo the account kept and forget their keys.

    For the account's deletion and for a withdrawn photo consent. A `StorageError` is raised
    as is: the caller refuses its own act, so no photo is left behind once it is said to be gone.
    Returns how many insights had a photo.
    """
    kept = (
        await db.scalars(
            select(Insight).where(Insight.user_id == user_id, Insight.photo_key.is_not(None))
        )
    ).all()
    for insight in kept:
        await remove(store, insight)
    await db.flush()
    return len(kept)


async def remove(store: PhotoStore, insight: Insight) -> None:
    """Delete both copies of the insight's photo and forget their keys; nothing when there is none."""
    if insight.photo_public_key is not None:
        await store.withdraw(insight.photo_public_key)
        insight.photo_public_key = None
    if insight.photo_key is not None:
        await store.remove(insight.photo_key)
        insight.photo_key = None
