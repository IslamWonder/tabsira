"""
Asking the one worker process to reconcile the public photo copies after a store failure.

A withdrawal or a moderator's removal answers the person at once (204), whatever the photo
store did; when the store failed, the public copy it should have deleted is still there. The
terms promise that it goes, so the failure asks the worker (`src/worker.py`, exactly one
process, AGENTS.md) to run `photo_service.reconcile_public_copies` shortly after, which
deletes every public copy nothing shows any more. The hourly timer (`src/cli/reconcile_photos.py`)
runs the same reconcile when no request ever reached the worker.

The routes never wait for the worker, and a queue that cannot take the request is only
logged: the timer covers it. A test replaces the queue with `use_retry_queue`.
"""

from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger("tabsira.photos")


class RetryQueue(Protocol):
    async def request(self) -> None:
        """Ask for one reconcile of the public copies."""


class TaskiqRetryQueue:
    """Kicks the worker's `photos.reconcile` task; the worker module is loaded on the first request."""

    async def request(self) -> None:
        from src.worker import reconcile_photos_task

        await reconcile_photos_task.kiq()


_queues: list[RetryQueue] = []


def use_retry_queue(queue: RetryQueue | None) -> None:
    """Make `queue` the one the requests go to; None goes back to the worker's."""
    _queues.clear()
    if queue is not None:
        _queues.append(queue)


def retry_queue() -> RetryQueue:
    if not _queues:
        _queues.append(TaskiqRetryQueue())
    return _queues[0]


async def request_retry() -> None:
    """Ask the worker to reconcile the public copies; a queue that is down is logged, never raised."""
    try:
        await retry_queue().request()
    except Exception as error:  # any queue failure: the timer covers it
        log.warning(
            "public photo copies: the reconcile could not be queued (%s); the timer will run it",
            type(error).__name__,
        )
