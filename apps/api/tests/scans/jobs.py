"""Run the jobs a test's queue collected, as the worker would, with a fake model and detector."""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.ai.records import CallLog
from src.pipeline.engine import InsightEngine
from src.pipeline.schemas import DetectorRequest, DetectorResult
from src.scans.engines import DemoEngine
from src.scans.workflow import ScanServices, run_scan
from tests.fakes import FakeModelClient


def scene_answer(**values: Any) -> dict[str, Any]:
    answer: dict[str, Any] = {
        "description": "نبتة صغيرة تحت المطر",
        "entities": [
            {
                "id": "e1",
                "label": "plant",
                "label_arabic": "نبتة",
                "detector_id": None,
                "box": [100, 100, 500, 600],
                "status": "observed",
            }
        ],
        "actions": [],
        "relations": [],
        "ambiguities": [],
        "clarification_question": None,
        "sensitive": [],
    }
    return answer | values


class NoDetector:
    async def detect(self, request: DetectorRequest) -> DetectorResult:
        del request
        return DetectorResult(available=False, latency_ms=0, error="unreachable")


async def run_queued(
    app: Any,
    maker: async_sessionmaker[AsyncSession],
    *,
    answers: list[Any] | None = None,
    engine: InsightEngine | None = None,
) -> None:
    """Run every run the application queued, then forget them."""
    model = FakeModelClient(answers=answers if answers is not None else [scene_answer()])

    def client_factory(log: CallLog) -> FakeModelClient:
        model.log = log
        return model

    async with httpx.AsyncClient() as http:
        services = ScanServices(
            settings=app.state.settings,
            sessionmaker=maker,
            redis=app.state.redis,
            http=http,
            client_factory=client_factory,
            engine_factory=lambda _deps: engine or DemoEngine(),
            detector=NoDetector(),
        )
        for scan_id, run in list(app.state.scan_queue.runs):
            await run_scan(services, scan_id, run)
    app.state.scan_queue.runs.clear()
