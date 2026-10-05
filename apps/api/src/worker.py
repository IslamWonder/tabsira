"""
The scan worker: one process that runs scan jobs from the Redis queue.

    uv run python -m src.cli.scan_worker

One process is enough and keeps scheduled work in one place (AGENTS.md); it
runs several scans at once on its event loop. It shares nothing with the API
processes but the database and Redis. The services a job needs (database,
Redis, HTTP, the provider client, the detector, the engine) are built on the
first job and closed when the worker stops.

It also runs the one other queued job: reconciling the public photo copies
after the photo store failed an API request (`services/photo_reconcile.py`).
"""

from __future__ import annotations

import asyncio

import httpx
from taskiq import TaskiqEvents, TaskiqState
from taskiq_redis import RedisStreamBroker

from src.ai.client import ModelClient, client_for
from src.ai.records import CallLog
from src.config import get_settings
from src.database import dispose_engine, get_sessionmaker
from src.pipeline.detector import DetectorClient
from src.redis_client import close_redis, get_redis
from src.scans.engines import engine_factory
from src.scans.workflow import ScanServices, run_scan
from src.services import photo_service
from src.storage.photos import build_photo_store
from src.storage.sounds import SoundStore

QUEUE = "tabsira:scans"
CONSUMER_GROUP = "tabsira-scan-workers"
# An unacknowledged job (its worker died) is handed out again after this.
IDLE_TIMEOUT_MS = 600_000
# Above the slowest model call, so a stuck connection is noticed.
HTTP_TIMEOUT_SECONDS = 120.0
# A store that just failed a request is given this long before it is asked again; the API
# request that asked has committed its state by then, so the reconcile sees it.
RECONCILE_DELAY_SECONDS = 30.0
# The stream read blocks on the server for two seconds at a time; the socket waits far longer
# than any stretch the event loop is busy (a first scan builds its indexes for seconds). At
# redis-py's five seconds, a read that timed out meanwhile stopped the worker, and its job came
# back only after IDLE_TIMEOUT_MS. A Redis that is gone is still noticed by the health check.
QUEUE_SOCKET_TIMEOUT_SECONDS = 60.0
QUEUE_HEALTH_CHECK_SECONDS = 30

_settings = get_settings()
broker = RedisStreamBroker(
    url=_settings.redis_connection_url(),
    queue_name=QUEUE,
    consumer_group_name=CONSUMER_GROUP,
    # A group made after jobs were queued still reads them.
    consumer_id="0",
    idle_timeout=IDLE_TIMEOUT_MS,
    maxlen=10_000,
    socket_timeout=QUEUE_SOCKET_TIMEOUT_SECONDS,
    health_check_interval=QUEUE_HEALTH_CHECK_SECONDS,
)

_services: list[ScanServices] = []


def build_services() -> ScanServices:
    """Build what jobs share, from the process settings."""
    settings = get_settings()
    http = httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS)

    def client_factory(log: CallLog) -> ModelClient:
        return client_for(settings, http, log=log)

    return ScanServices(
        settings=settings,
        sessionmaker=get_sessionmaker(),
        redis=get_redis(settings),
        http=http,
        client_factory=client_factory,
        engine_factory=engine_factory(settings),
        detector=DetectorClient(
            settings.detector_url, http, timeout_seconds=settings.detector_timeout_seconds
        ),
        sounds=SoundStore.from_settings(settings),
    )


def services() -> ScanServices:
    if not _services:
        _services.append(build_services())
    return _services[0]


@broker.task(task_name="scan.run")
async def run_scan_task(scan_id: int, run: int) -> None:
    """Run one run of a scan."""
    await run_scan(services(), scan_id, run)


@broker.task(task_name="photos.reconcile")
async def reconcile_photos_task() -> None:
    """Delete the public photo copies nothing shows, a little after a store failure."""
    await asyncio.sleep(RECONCILE_DELAY_SECONDS)
    shared = services()
    async with shared.sessionmaker() as db, db.begin():
        report = await photo_service.reconcile_public_copies(db, build_photo_store(shared.settings))
    photo_service.log.info(
        "public photo copies reconciled: %d checked, %d deleted, %d failed%s",
        report.checked,
        report.deleted,
        report.failed,
        " (skipped: another run holds the lock)" if report.skipped else "",
    )


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def close_services(_state: TaskiqState) -> None:
    """Close the HTTP client, Redis and the database when the worker stops."""
    while _services:
        await _services.pop().http.aclose()
    await close_redis()
    await dispose_engine()
