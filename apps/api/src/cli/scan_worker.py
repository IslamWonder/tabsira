"""
The scan worker: the one process that runs scan jobs from the Redis queue.

    uv run python -m src.cli.scan_worker

Queued work runs in exactly one process (AGENTS.md), never inside the API's
gunicorn workers: they are replaced one at a time and booted once more on a
spare port before each deploy, and every one of them would lease jobs. This
process reads the queue's Redis stream as one consumer and runs up to
`MAX_CONCURRENT_SCANS` scans at once on its event loop.

SIGTERM or SIGINT stop it gracefully: it stops taking jobs, lets the running
ones finish for up to SCAN_JOB_TIMEOUT_SECONDS, then closes its connections. A
job it could not finish stays unacknowledged on the stream and is handed out
again after ten minutes; running a job twice changes nothing
(`src/scans/workflow.py`). Exits 0 after a graceful stop.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Callable, Sequence
from typing import Any

from taskiq.receiver import Receiver

from src.config import get_settings

log = logging.getLogger("tabsira.scan_worker")

# Scans one process runs at once: each mostly waits on a model or the detector.
MAX_CONCURRENT_SCANS = 4
STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT)

ReceiverFactory = Callable[..., Any]


async def serve(stop: asyncio.Event, *, receiver_factory: ReceiverFactory = Receiver) -> None:
    """Run jobs until `stop` is set, then finish the running ones and close everything."""
    from src.worker import broker

    broker.is_worker_process = True
    receiver = receiver_factory(
        broker,
        max_async_tasks=MAX_CONCURRENT_SCANS,
        run_startup=True,
        wait_tasks_timeout=get_settings().scan_job_timeout_seconds,
    )
    log.info("scan worker started")
    try:
        await receiver.listen(stop)
    finally:
        # Runs the worker's shutdown handlers: HTTP, Redis and the database are closed.
        await broker.shutdown()
        log.info("scan worker stopped")


async def run(*, receiver_factory: ReceiverFactory = Receiver) -> int:
    """Serve until a stop signal arrives; return the exit code."""
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for stop_signal in STOP_SIGNALS:
        loop.add_signal_handler(stop_signal, stop.set)
    try:
        await serve(stop, receiver_factory=receiver_factory)
    finally:
        for stop_signal in STOP_SIGNALS:
            loop.remove_signal_handler(stop_signal)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the worker; `argv` is accepted for symmetry with the other commands."""
    del argv
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
