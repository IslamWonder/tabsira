"""
Count a view of a post once per viewer a day, and only views people make.

- Only the beacon the post page sends once it has opened (`POST /posts/{id}/view`) counts.
  Reading a post never does: the web server's render, link previews and crawlers fetching the
  page do not move the number.
- One view per viewer per 24 hours. A signed-in viewer is their account and their address; a
  guest is their address (cut to its /64 for IPv6, as every limit here). People who share an
  address count once together that day.
- The author never counts. Signed in, they are known; their own opening also marks their
  address for that post, so the same person signed out on the same day is not counted either.
  No session is looked up: whether an address is the author's is never asked, so the count
  cannot tell a neighbour on the same network who wrote a post.
- Known bots and scripts, by user agent, never count; neither does a request with none. The
  user agent is read, not kept.
- If Redis is down nothing is counted, rather than everything.

What Redis keeps for the window is a keyed hash of the post and the viewer, with a purpose of its
own (`VIEW_PURPOSE`): it names neither the account nor the address, and joins with nothing else
the API stores. The keys expire after 24 hours. The post keeps a number only.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import timedelta

from redis.asyncio import Redis
from redis.exceptions import RedisError, WatchError
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src import security
from src.models.social import Post
from src.models.user import User

logger = logging.getLogger(__name__)

VIEW_WINDOW = timedelta(hours=24)
VIEW_PURPOSE = "post-view"
KEY_PREFIX = "tabsira:view"

# Crawlers, link unfurlers, headless browsers and HTTP libraries. "bot" alone catches Googlebot,
# bingbot, Twitterbot, Discordbot, Slackbot, TelegramBot and WhatsApp's own.
BOT_USER_AGENT = re.compile(
    r"bot\b|bot/|crawl|spider|slurp|preview|facebookexternalhit|whatsapp|embedly|"
    r"headless|lighthouse|pagespeed|python-|curl/|wget|httpx|okhttp|go-http|java/|"
    r"^node$|node-fetch|axios/|undici",
    re.IGNORECASE,
)


def is_bot(user_agent: str | None) -> bool:
    """Tell whether the user agent is missing or names a crawler or a script."""
    return not user_agent or BOT_USER_AGENT.search(user_agent) is not None


def marker(hash_key: bytes, post_id: int, viewer: str) -> str:
    """Return the Redis key that remembers `viewer` saw the post: a keyed hash nobody can read."""
    return f"{KEY_PREFIX}:{security.keyed_hash(hash_key, VIEW_PURPOSE, f'{post_id}:{viewer}')}"


def _markers(hash_key: bytes, post_id: int, viewer_id: uuid.UUID | None, ip_hash: str) -> list[str]:
    keys = [marker(hash_key, post_id, f"ip:{ip_hash}")]
    if viewer_id is not None:
        keys.append(marker(hash_key, post_id, f"user:{viewer_id}"))
    return keys


def _seconds() -> int:
    return int(VIEW_WINDOW.total_seconds())


async def _first_in_window(redis: Redis, keys: list[str]) -> bool:
    """
    Remember KEYS for the window; True when none of them was there yet.

    Checked and set in one transaction: a twin request that sets one of them in between makes
    this one fail, so two tabs or two accounts on one address count once.
    """
    try:
        async with redis.pipeline(transaction=True) as pipe:
            await pipe.watch(*keys)
            if any(value is not None for value in await pipe.mget(keys)):
                return False
            # redis-py ships `multi` without type hints.
            pipe.multi()  # type: ignore[no-untyped-call]
            for key in keys:
                pipe.set(key, "1", ex=_seconds())
            await pipe.execute()
    except WatchError:
        return False
    except RedisError:
        logger.warning("view not counted: Redis did not answer")
        return False
    return True


async def _mark_author_address(redis: Redis, key: str) -> None:
    try:
        await redis.set(key, "1", ex=_seconds())
    except RedisError:
        logger.warning("author's view not marked: Redis did not answer")


async def counts(
    redis: Redis,
    hash_key: bytes,
    post: Post,
    viewer: User | None,
    *,
    ip_hash: str,
    user_agent: str | None,
) -> bool:
    """
    Return True when this view should be counted, and remember the viewer for the window.

    False for the author (whose address is marked instead), a bot, a viewer already seen in the
    window, or when Redis cannot answer.
    """
    if is_bot(user_agent):
        return False
    keys = _markers(hash_key, post.id, viewer.id if viewer is not None else None, ip_hash)
    if viewer is not None and viewer.id == post.author_id:
        await _mark_author_address(redis, keys[0])
        return False
    return await _first_in_window(redis, keys)


async def record(
    db: AsyncSession,
    redis: Redis,
    hash_key: bytes,
    post: Post,
    viewer: User | None,
    *,
    ip_hash: str,
    user_agent: str | None,
) -> None:
    """Add one view to the post when it counts; nothing else is written."""
    if not await counts(redis, hash_key, post, viewer, ip_hash=ip_hash, user_agent=user_agent):
        return
    # In SQL, from the row's own value, so two viewers at once are two views. A view is not an
    # edit: `updated_at` keeps its value.
    await db.execute(
        update(Post)
        .where(Post.id == post.id)
        .values(views_count=Post.views_count + 1, updated_at=Post.updated_at)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
