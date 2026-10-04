"""
The process's Redis client (decision 21).

Redis carries what PostgreSQL does poorly and nothing durable: the progress of
a scan for whichever worker holds the reader's stream, the photo of a scan for
the hour it is needed, and the queue of scan jobs. A Redis that is down fails
the request that needs it with a stable code; the rest of the API keeps working.
"""

from __future__ import annotations

from redis.asyncio import Redis

from src.config import Settings

# Connecting must not hang a request: a Redis that is down answers within this.
CONNECT_TIMEOUT_SECONDS = 2.0

_clients: dict[str, Redis] = {}


def get_redis(settings: Settings) -> Redis:
    """Return the client of REDIS_URL, built on first use and shared by the process."""
    url = settings.redis_connection_url()
    client = _clients.get(url)
    if client is None:
        client = Redis.from_url(
            url,
            socket_connect_timeout=CONNECT_TIMEOUT_SECONDS,
            health_check_interval=30,
        )
        _clients[url] = client
    return client


async def close_redis() -> None:
    """Close every client this process opened; called when it stops."""
    clients = list(_clients.values())
    _clients.clear()
    for client in clients:
        await client.aclose()
