"""
Honest progress of a scan, published on Redis so any API worker can serve the reader's stream.

The job publishes each event twice in one transaction: appended to a short list
(`scan:<id>:events`, the replay for a reader who reconnects with
`Last-Event-ID`) and sent on the channel `scan:<id>` (for readers already
connected). Every event carries a number that grows by one, so a reader skips
what it has already seen whichever way an event reaches it. The list and the
counter expire after SCAN_EVENTS_TTL_SECONDS. A stream ends with the first
terminal event (`done` or `failed`) or after its longest life; the reader then
reconnects and is answered from the list or from the database.

Events: `queued` {run}; `stage` {run, stage, state} where stage is one of the
four honest stages of v2 §4 (understanding, searching, verifying, composing)
and state is `started`, `done` or `failed`; `done` {run, outcome, insight_ids};
`failed` {run, code}.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

from pydantic import BaseModel
from redis.asyncio import Redis

from src.clock import monotonic

TERMINAL = frozenset({"done", "failed"})
# The replay keeps this many events, far more than one run publishes.
MAX_EVENTS = 64
# How long a stream waits for a message before it checks its life again.
POLL_SECONDS = 1.0


class ProgressEvent(BaseModel):
    id: int
    event: str
    data: dict[str, Any]

    @property
    def terminal(self) -> bool:
        return self.event in TERMINAL

    @property
    def run(self) -> int:
        value = self.data.get("run", 0)
        return value if isinstance(value, int) else 0

    def as_sse(self) -> dict[str, str]:
        return {
            "id": str(self.id),
            "event": self.event,
            "data": json.dumps(self.data, ensure_ascii=False, separators=(",", ":")),
        }


def events_key(scan_id: uuid.UUID) -> str:
    return f"scan:{scan_id}:events"


def sequence_key(scan_id: uuid.UUID) -> str:
    return f"scan:{scan_id}:seq"


def channel(scan_id: uuid.UUID) -> str:
    return f"scan:{scan_id}"


async def publish(
    redis: Redis, scan_id: uuid.UUID, event: str, data: dict[str, Any], *, ttl: int
) -> ProgressEvent:
    """Give an event its number, keep it for replay and send it to the readers of the scan."""
    number = int(await redis.incr(sequence_key(scan_id)))
    published = ProgressEvent(id=number, event=event, data=data)
    payload = published.model_dump_json()
    async with redis.pipeline(transaction=True) as pipe:
        pipe.rpush(events_key(scan_id), payload)
        pipe.ltrim(events_key(scan_id), -MAX_EVENTS, -1)
        pipe.expire(events_key(scan_id), ttl)
        pipe.expire(sequence_key(scan_id), ttl)
        pipe.publish(channel(scan_id), payload)
        await pipe.execute()
    return published


async def replay(redis: Redis, scan_id: uuid.UUID, after: int = 0) -> list[ProgressEvent]:
    """Return the kept events numbered above `after`, in order."""
    raw = await redis.lrange(events_key(scan_id), 0, -1)
    events = [ProgressEvent.model_validate_json(item) for item in raw]
    return [event for event in events if event.id > after]


def parse_last_event_id(value: str | None) -> int:
    """Read a `Last-Event-ID`; anything that is not a small number counts as none."""
    if value is None or not value.strip().isdigit() or len(value.strip()) > 18:
        return 0
    return int(value.strip())


async def stream(
    redis: Redis,
    scan_id: uuid.UUID,
    *,
    run: int,
    after: int,
    fallback: ProgressEvent | None,
    max_seconds: float,
    clock: Callable[[], float] = monotonic,
) -> AsyncIterator[ProgressEvent]:
    """
    Yield the events of run `run` numbered above `after` until a terminal one, or for `max_seconds`.

    The channel is joined before the replay is read, so an event published in
    between is seen at least once and its number keeps it from being shown twice.
    Events of an earlier run (before a focus or a clarification) are skipped.
    `fallback` is the terminal event the database knows, yielded when the run
    has ended but its events have expired.
    """
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel(scan_id))
    started = clock()
    last = after
    try:
        for event in await replay(redis, scan_id, after):
            last = event.id
            if event.run < run:
                continue
            yield event
            if event.terminal:
                return
        if fallback is not None:
            yield fallback
            return
        while clock() - started < max_seconds:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=POLL_SECONDS)
            if message is None:
                continue
            event = ProgressEvent.model_validate_json(message["data"])
            if event.id <= last or event.run < run:
                continue
            last = event.id
            yield event
            if event.terminal:
                return
    finally:
        await pubsub.unsubscribe(channel(scan_id))
        await pubsub.aclose()  # type: ignore[no-untyped-call]
