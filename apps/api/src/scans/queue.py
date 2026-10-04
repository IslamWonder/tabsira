"""
The queue the API puts scan jobs on.

Jobs travel on a Redis stream read by one worker process (`src/worker.py`,
run with `taskiq worker src.worker:broker --workers 1`). A job is acknowledged
once it has run; one left unacknowledged by a worker that died is handed out
again after ten minutes, and the job itself makes a second run harmless
(`src/scans/workflow.py`). The routes depend on `ScanQueue`, so a test puts its
own queue in `app.state.scan_queue`.
"""

from __future__ import annotations

from typing import Protocol

from fastapi import Request


class ScanQueue(Protocol):
    async def enqueue(self, scan_id: int, run: int) -> None:
        """Ask for one run of a scan."""


class QueueUnavailableError(Exception):
    """The job could not be put on the queue."""


class TaskiqScanQueue:
    """Kicks the worker's `scan.run` task; the worker module is loaded on the first job."""

    def __init__(self) -> None:
        self.used = False

    async def enqueue(self, scan_id: int, run: int) -> None:
        from src.worker import run_scan_task

        self.used = True
        try:
            await run_scan_task.kiq(scan_id, run)
        except Exception as error:
            raise QueueUnavailableError(type(error).__name__) from None


_queues: list[TaskiqScanQueue] = []


async def close_queue() -> None:
    """Close the queue's Redis connections in a process that used it."""
    if any(queue.used for queue in _queues):
        from src.worker import broker

        await broker.shutdown()
    _queues.clear()


def get_scan_queue(request: Request) -> ScanQueue:
    """Return the application's queue: the one a test set, else the worker's."""
    queue: ScanQueue | None = getattr(request.app.state, "scan_queue", None)
    if queue is None:
        made = TaskiqScanQueue()
        _queues.append(made)
        request.app.state.scan_queue = made
        return made
    return queue
