"""The worker process and the queue the API puts jobs on."""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from src import worker
from src.ai.client import ProviderClient
from src.ai.records import CallLog
from src.pipeline.detector import DetectorClient
from src.scans import queue as scan_queue
from src.scans.queue import QueueUnavailableError, TaskiqScanQueue, get_scan_queue


def test_the_worker_reads_one_stream_as_one_group():
    assert worker.broker.queue_name == worker.QUEUE
    assert worker.broker.consumer_group_name == worker.CONSUMER_GROUP
    assert worker.broker.consumer_id == "0"
    assert worker.broker.idle_timeout == worker.IDLE_TIMEOUT_MS


async def test_the_worker_builds_its_services_once_and_closes_them(monkeypatch):
    closed: list[str] = []

    async def close_redis() -> None:
        closed.append("redis")

    async def dispose_engine() -> None:
        closed.append("database")

    monkeypatch.setattr(worker, "close_redis", close_redis)
    monkeypatch.setattr(worker, "dispose_engine", dispose_engine)
    worker._services.clear()

    services = worker.services()

    assert worker.services() is services
    assert isinstance(services.detector, DetectorClient)
    assert isinstance(services.client_factory(CallLog()), ProviderClient)
    await worker.close_services(None)  # type: ignore[arg-type]
    assert worker._services == []
    assert services.http.is_closed
    assert closed == ["redis", "database"]


async def test_the_task_runs_the_scan_it_names(monkeypatch):
    ran: list[tuple[object, uuid.UUID, int]] = []

    async def run_scan(services, scan_id, run):
        ran.append((services, scan_id, run))

    monkeypatch.setattr(worker, "run_scan", run_scan)
    monkeypatch.setattr(worker, "services", lambda: "services")
    scan_id = uuid.uuid4()

    await worker.run_scan_task.original_func(str(scan_id), 2)

    assert ran == [("services", scan_id, 2)]


async def test_the_api_kicks_the_task_and_reports_a_queue_that_is_down(monkeypatch):
    kicked: list[tuple[str, int]] = []

    async def kiq(scan_id: str, run: int) -> None:
        kicked.append((scan_id, run))

    monkeypatch.setattr(worker.run_scan_task, "kiq", kiq)
    queue = TaskiqScanQueue()
    scan_id = uuid.uuid4()

    await queue.enqueue(scan_id, 1)
    assert kicked == [(str(scan_id), 1)]
    assert queue.used

    async def broken(scan_id: str, run: int) -> None:
        message = "connection refused"
        raise ConnectionError(message)

    monkeypatch.setattr(worker.run_scan_task, "kiq", broken)
    with pytest.raises(QueueUnavailableError, match="ConnectionError"):
        await queue.enqueue(scan_id, 1)


async def test_the_application_has_one_queue_and_closes_it_when_used(monkeypatch):
    shut: list[bool] = []

    async def shutdown() -> None:
        shut.append(True)

    monkeypatch.setattr(worker.broker, "shutdown", shutdown)
    app = FastAPI()
    request = Request({"type": "http", "app": app})

    made = get_scan_queue(request)
    assert isinstance(made, TaskiqScanQueue)
    assert get_scan_queue(request) is made
    await scan_queue.close_queue()
    assert shut == []

    used = get_scan_queue(Request({"type": "http", "app": FastAPI()}))
    used.used = True  # type: ignore[attr-defined]
    await scan_queue.close_queue()
    assert shut == [True]
