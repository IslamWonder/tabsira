"""`python -m src.cli.scan_worker`: one consumer process, stopped gracefully by SIGTERM."""

from __future__ import annotations

import asyncio
import os
import signal

import pytest

from src import worker
from src.cli import scan_worker


class FakeReceiver:
    """Listens until the stop event is set; `on_listen` runs first."""

    def __init__(self, on_listen=None) -> None:
        self.on_listen = on_listen
        self.made_with: dict = {}
        self.stopped = False

    def __call__(self, broker, **kwargs):
        self.made_with = {"broker": broker, **kwargs}
        return self

    async def listen(self, stop: asyncio.Event) -> None:
        if self.on_listen is not None:
            self.on_listen(stop)
        await stop.wait()
        self.stopped = True


@pytest.fixture
def shutdowns(monkeypatch):
    calls: list[bool] = []

    async def shutdown() -> None:
        calls.append(True)

    monkeypatch.setattr(worker.broker, "shutdown", shutdown)
    monkeypatch.setattr(worker.broker, "is_worker_process", False)
    return calls


async def test_the_worker_runs_jobs_until_told_to_stop_then_closes(shutdowns, flow_settings):
    receiver = FakeReceiver(on_listen=lambda stop: asyncio.get_running_loop().call_soon(stop.set))

    await scan_worker.serve(asyncio.Event(), receiver_factory=receiver)

    assert receiver.stopped
    assert receiver.made_with["broker"] is worker.broker
    assert receiver.made_with["max_async_tasks"] == scan_worker.MAX_CONCURRENT_SCANS
    assert receiver.made_with["run_startup"] is True
    assert receiver.made_with["wait_tasks_timeout"] == 240.0
    assert worker.broker.is_worker_process is True
    assert shutdowns == [True]


async def test_sigterm_stops_the_worker_gracefully(shutdowns):
    receiver = FakeReceiver(on_listen=lambda _stop: os.kill(os.getpid(), signal.SIGTERM))

    assert await scan_worker.run(receiver_factory=receiver) == 0

    assert receiver.stopped
    assert shutdowns == [True]


async def test_a_loop_without_signal_handlers_still_stops_on_sigterm(shutdowns, monkeypatch):
    """Windows: the event loop refuses signal handlers; a plain one takes over."""
    loop = asyncio.get_running_loop()

    def refuse(*_args, **_kwargs):
        raise NotImplementedError

    monkeypatch.setattr(loop, "add_signal_handler", refuse)
    before = {
        stop_signal: signal.getsignal(stop_signal) for stop_signal in scan_worker.STOP_SIGNALS
    }
    receiver = FakeReceiver(on_listen=lambda _stop: signal.raise_signal(signal.SIGTERM))

    assert await scan_worker.run(receiver_factory=receiver) == 0

    assert receiver.stopped
    assert shutdowns == [True]
    assert {s: signal.getsignal(s) for s in scan_worker.STOP_SIGNALS} == before


def test_main_runs_the_worker(monkeypatch):
    async def run() -> int:
        return 0

    monkeypatch.setattr(scan_worker, "run", run)

    assert scan_worker.main([]) == 0
