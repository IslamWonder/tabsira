"""FastAPI dependencies of the scan workflow: Redis, the queue, the photo fetcher, feature flags."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Path, Request
from redis.asyncio import Redis

from src.deps import IpHashDep, SettingsDep
from src.errors import AppError, ErrorCode
from src.redis_client import get_redis
from src.scans.fetch import fetch_client, fetch_image
from src.scans.queue import ScanQueue, get_scan_queue
from src.schemas.public_id import MAX_PUBLIC_ID
from src.services.window_limiter import AddressLimits, limits_of, too_many_requests

ImageFetcher = Callable[[str], Awaitable[bytes]]
# A public id in a path (decision 37): a positive 64-bit number.
PublicIdPath = Annotated[int, Path(ge=1, le=MAX_PUBLIC_ID)]


def app_redis(request: Request, settings: SettingsDep) -> Redis:
    """Return the Redis client a test set on the application, else the process's."""
    client: Redis | None = getattr(request.app.state, "redis", None)
    return client if client is not None else get_redis(settings)


def image_fetcher(request: Request, settings: SettingsDep) -> ImageFetcher:
    """Return the fetcher of photo addresses: the guarded one, or a test's."""
    fetcher: ImageFetcher | None = getattr(request.app.state, "image_fetcher", None)
    if fetcher is not None:
        return fetcher

    async def fetch(url: str) -> bytes:
        async with fetch_client(settings) as client:
            return await fetch_image(url, settings, client=client)

    return fetch


RedisDep = Annotated[Redis, Depends(app_redis)]
QueueDep = Annotated[ScanQueue, Depends(get_scan_queue)]
FetcherDep = Annotated[ImageFetcher, Depends(image_fetcher)]


# Every scan and every chat answer costs model calls, and anyone may start one
# as a guest, so each is limited per address and over all addresses, per API
# worker, in the fixed windows of `window_limiter` (a spam bound, not a quota).
SCAN_LIMITS = ("scan_limits", 30, 600, 3600.0)
CHAT_LIMITS = ("chat_limits", 60, 1200, 3600.0)
# Keeping a tutorial insight makes a guest: bounded the same way, more loosely.
KEEP_LIMITS = ("keep_limits", 60, 1200, 3600.0)


def address_limit(
    limits: tuple[str, int, int, float], detail: str
) -> Callable[[Request, IpHashDep], None]:
    """Return a dependency that answers 429 once an address, or the worker, has used its budget."""
    name, per_address, overall, window = limits

    def check(request: Request, ip_hash: IpHashDep) -> None:
        budget = limits_of(request, name, lambda: AddressLimits(per_address, overall, window))
        retry_after = budget.hit(ip_hash)
        if retry_after is not None:
            raise too_many_requests(retry_after, detail)

    return check


def feature(name: str) -> Callable[[SettingsDep], None]:
    """Return a dependency that answers 404 FEATURE_DISABLED while FEATURE_<NAME> is off."""

    def check(settings: SettingsDep) -> None:
        if not getattr(settings, f"feature_{name}"):
            raise AppError(
                ErrorCode.FEATURE_DISABLED, f"The {name} feature is switched off.", status_code=404
            )

    return check
