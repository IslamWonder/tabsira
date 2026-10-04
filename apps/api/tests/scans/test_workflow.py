"""The scan job: detector, scene, sensitivity and engine, run once whatever happens."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, update

from src.ai.errors import AiCallError, AiErrorCode
from src.ai.records import CallLog
from src.models import (
    AiCall,
    Guest,
    Insight,
    Scan,
    ScanEvent,
    ScanOutcome,
    ScanStatus,
)
from src.owner import Owner
from src.pipeline.engine import (
    EngineRequest,
    EngineResult,
    EngineStage,
    EngineStatus,
    HadithRef,
    ProgressCallback,
)
from src.pipeline.image_validator import validate_image
from src.pipeline.schemas import BBox, DetectorRequest, DetectorResult, ImageUpload
from src.scans import buffer, progress, workflow
from src.scans.engines import DemoEngine, EngineDeps
from src.scans.workflow import ScanServices, apply_focus, run_scan
from tests.fakes import FakeModelClient
from tests.scans.builders import entity, proposed, scan_row, scene
from tests.scans.conftest import photo

GUEST = "f" * 64


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


class FakeDetector:
    def __init__(self, available: bool = False) -> None:
        self.available = available
        self.requests: list[DetectorRequest] = []

    async def detect(self, request: DetectorRequest) -> DetectorResult:
        self.requests.append(request)
        if self.available:
            return DetectorResult(available=True, model="fake", latency_ms=3)
        return DetectorResult(available=False, latency_ms=1, error="unreachable")


class StaticEngine:
    """Reports the engine stages, then answers what it was given."""

    def __init__(self, result: EngineResult | Exception, stages: bool = True) -> None:
        self.result = result
        self.stages = stages
        self.requests: list[EngineRequest] = []

    async def propose(
        self, request: EngineRequest, on_stage: ProgressCallback | None = None
    ) -> EngineResult:
        self.requests.append(request)
        if self.stages and on_stage is not None:
            await on_stage(EngineStage.SEARCHING)
            await on_stage(EngineStage.COMPOSING)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest_asyncio.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


def services_for(
    store, redis, http, settings, engine, *, answers=None, detector=None, model=None
) -> tuple[ScanServices, FakeModelClient]:
    fake = model or FakeModelClient(answers=answers if answers is not None else [scene_answer()])

    def client_factory(log: CallLog) -> FakeModelClient:
        fake.log = log
        return fake

    def engine_factory(deps: EngineDeps):
        assert deps.client is fake
        return engine

    return (
        ScanServices(
            settings=settings,
            sessionmaker=store,
            redis=redis,
            http=http,
            client_factory=client_factory,
            engine_factory=engine_factory,
            detector=detector or FakeDetector(),
        ),
        fake,
    )


async def new_scan(store, redis, *, keep_photo: bool = True, **values: Any) -> int:
    async with store() as db:
        if await db.get(Guest, GUEST) is None:
            db.add(Guest(key=GUEST))
            await db.flush()
        scan = scan_row(Owner(guest_key=GUEST), **values)
        db.add(scan)
        await db.commit()
        scan_id = scan.id
    if keep_photo:
        image = validate_image(ImageUpload(data=photo()), max_bytes=10**7, max_pixels=10**7)
        await buffer.put(redis, scan_id, full=image.image, model=image.model_image, ttl=600)
    return scan_id


async def the_scan(store, scan_id) -> Scan:
    async with store() as db:
        return (await db.scalars(select(Scan).where(Scan.id == scan_id))).one()


async def events(redis, scan_id) -> list[tuple[str, dict[str, Any]]]:
    return [(event.event, event.data) for event in await progress.replay(redis, scan_id)]


async def test_a_scan_runs_through_every_stage_and_saves_its_insights(
    store, redis, http, flow_settings
):
    scan_id = await new_scan(store, redis)
    detector = FakeDetector(available=True)
    engine = StaticEngine(
        EngineResult(
            status=EngineStatus.OK,
            insights=[proposed()],
            awaiting_ruling=[HadithRef(collection="bukhari", number="1032")],
            stage_ms={EngineStage.SEARCHING: 40},
        )
    )
    services, model = services_for(store, redis, http, flow_settings, engine, detector=detector)
    sent = await buffer.get(redis, scan_id, buffer.Copy.MODEL)

    await run_scan(services, scan_id, 1)

    scan = await the_scan(store, scan_id)
    assert (scan.status, scan.outcome, scan.error_code) == (
        ScanStatus.DONE,
        ScanOutcome.INSIGHTS,
        None,
    )
    assert scan.scene["description"] == "نبتة صغيرة تحت المطر"
    assert scan.awaiting_ruling == [{"collection": "bukhari", "number": "1032"}]
    assert not scan.sensitive
    async with store() as db:
        insights = (await db.scalars(select(Insight).where(Insight.scan_id == scan_id))).all()
        stages = (await db.scalars(select(ScanEvent).where(ScanEvent.scan_id == scan_id))).all()
        calls = (await db.scalars(select(AiCall).where(AiCall.scan_id == scan_id))).all()
    assert [(row.quran_surah, row.quran_ayah, row.hadith_number) for row in insights] == [
        (30, 50, "1032")
    ]
    assert insights[0].guest_key == GUEST
    assert insights[0].quran_evidence["matched_on"] == "إحياء الأرض"
    assert {(event.stage, event.status) for event in stages} >= {
        ("detect", "done"),
        ("understand", "done"),
        ("sensitivity", "done"),
        ("searching", "done"),
        ("save", "done"),
        ("job", "done"),
    }
    assert [(call.stage, call.ok) for call in calls] == [("vision", True)]
    assert detector.requests[0].image.width == 96
    assert model.calls[0]["images"][0].data == sent
    assert await buffer.get(redis, scan_id, buffer.Copy.MODEL) is None
    assert await buffer.get(redis, scan_id, buffer.Copy.FULL) is not None
    published = await events(redis, scan_id)
    assert [name for name, _ in published] == ["stage"] * 6 + ["done"]
    assert [(data["stage"], data["state"]) for name, data in published if name == "stage"] == [
        ("understanding", "started"),
        ("understanding", "done"),
        ("searching", "started"),
        ("searching", "done"),
        ("composing", "started"),
        ("composing", "done"),
    ]
    done = published[-1][1]
    assert done["outcome"] == "insights"
    assert done["insight_ids"] == [str(insights[0].id)]
    assert done["run"] == 1


async def test_a_sensitive_scene_drops_its_photo_at_once_and_keeps_its_meaning(
    store, redis, http, flow_settings
):
    scan_id = await new_scan(store, redis)
    engine = StaticEngine(EngineResult(status=EngineStatus.OK, insights=[proposed()]))
    services, _ = services_for(
        store, redis, http, flow_settings, engine, answers=[scene_answer(sensitive=["alcohol"])]
    )

    await run_scan(services, scan_id, 1)

    scan = await the_scan(store, scan_id)
    assert scan.sensitive
    assert scan.sensitive_categories == ["alcohol"]
    assert scan.outcome is ScanOutcome.INSIGHTS
    assert await buffer.get(redis, scan_id, buffer.Copy.FULL) is None
    assert await buffer.get(redis, scan_id, buffer.Copy.MODEL) is None


async def test_a_scan_already_run_elsewhere_or_of_another_run_is_left_alone(
    store, redis, http, flow_settings
):
    scan_id = await new_scan(store, redis)
    engine = StaticEngine(EngineResult(status=EngineStatus.OK, insights=[proposed()]))
    services, model = services_for(store, redis, http, flow_settings, engine)

    await redis.set(workflow.lock_key(scan_id), 1)
    await run_scan(services, scan_id, 1)
    await redis.delete(workflow.lock_key(scan_id))
    await run_scan(services, scan_id, 2)

    assert (await the_scan(store, scan_id)).status is ScanStatus.QUEUED
    assert model.calls == []
    assert await redis.get(workflow.lock_key(scan_id)) is None

    await run_scan(services, scan_id, 1)
    await run_scan(services, scan_id, 1)
    assert len(engine.requests) == 1


@pytest.mark.parametrize(
    ("answer", "code", "reason"),
    [
        (AiCallError(AiErrorCode.INVALID_OUTPUT, "bad"), "VISION_FAILED", "invalid_output"),
        (AiCallError(AiErrorCode.NETWORK, "down"), "MODEL_UNAVAILABLE", "network"),
        (
            scene_answer(description="قال تعالى: «فانظر إلى آثار رحمت الله كيف»"),
            "VISION_FAILED",
            "leak",
        ),
    ],
)
async def test_a_scene_that_cannot_be_understood_fails_the_scan_honestly(
    store, redis, http, flow_settings, answer, code, reason
):
    scan_id = await new_scan(store, redis)
    services, _ = services_for(
        store,
        redis,
        http,
        flow_settings,
        StaticEngine(EngineResult(status=EngineStatus.OK)),
        answers=[answer],
    )

    await run_scan(services, scan_id, 1)

    scan = await the_scan(store, scan_id)
    assert (scan.status, scan.error_code) == (ScanStatus.FAILED, code)
    assert (await events(redis, scan_id))[-1] == ("failed", {"run": 1, "code": code})
    async with store() as db:
        stages = (await db.scalars(select(ScanEvent).where(ScanEvent.scan_id == scan_id))).all()
    assert ("understand", "failed", reason) in {(e.stage, e.status, e.code) for e in stages}
    # No verdict was reached: no copy of the photo is kept at all.
    assert await buffer.get(redis, scan_id, buffer.Copy.MODEL) is None
    assert await buffer.get(redis, scan_id, buffer.Copy.FULL) is None


async def test_a_photo_that_left_the_store_fails_as_a_missing_asset(
    store, redis, http, flow_settings
):
    scan_id = await new_scan(store, redis, keep_photo=False)
    services, _ = services_for(
        store, redis, http, flow_settings, StaticEngine(EngineResult(status=EngineStatus.OK))
    )

    await run_scan(services, scan_id, 1)

    assert (await the_scan(store, scan_id)).error_code == "ASSET_MISSING"


@pytest.mark.parametrize(
    ("result", "code"),
    [
        (EngineResult(status=EngineStatus.SOURCE_UNAVAILABLE), "SOURCE_UNAVAILABLE"),
        (EngineResult(status=EngineStatus.MODEL_UNAVAILABLE), "MODEL_UNAVAILABLE"),
        (AiCallError(AiErrorCode.RATE_LIMITED, "busy"), "MODEL_UNAVAILABLE"),
        (RuntimeError("bug"), "INTERNAL_ERROR"),
    ],
)
async def test_an_engine_that_cannot_answer_fails_the_scan_with_its_code(
    store, redis, http, flow_settings, result, code
):
    scan_id = await new_scan(store, redis)
    services, _ = services_for(store, redis, http, flow_settings, StaticEngine(result))

    await run_scan(services, scan_id, 1)

    scan = await the_scan(store, scan_id)
    assert (scan.status, scan.error_code) == (ScanStatus.FAILED, code)


@pytest.mark.parametrize(
    ("result", "outcome", "question"),
    [
        (
            EngineResult(
                status=EngineStatus.NEEDS_CLARIFICATION,
                clarification_question=" ماذا يفعل الشخص بالهاتف؟ ",
            ),
            ScanOutcome.NEEDS_CLARIFICATION,
            "ماذا يفعل الشخص بالهاتف؟",
        ),
        (
            EngineResult(
                status=EngineStatus.NEEDS_CLARIFICATION,
                clarification_question="قال تعالى: «إنا أنزلناه في ليلة القدر»",
            ),
            ScanOutcome.NO_RELEVANT_EVIDENCE,
            None,
        ),
        (
            EngineResult(status=EngineStatus.NEEDS_CLARIFICATION),
            ScanOutcome.NO_RELEVANT_EVIDENCE,
            None,
        ),
        (
            EngineResult(status=EngineStatus.NO_RELEVANT_EVIDENCE),
            ScanOutcome.NO_RELEVANT_EVIDENCE,
            None,
        ),
        (
            EngineResult(status=EngineStatus.OK, insights=[proposed(quran=None, hadith=None)]),
            ScanOutcome.NO_RELEVANT_EVIDENCE,
            None,
        ),
    ],
)
async def test_a_scan_without_insights_ends_with_a_question_or_an_honest_no_result(
    store, redis, http, flow_settings, result, outcome, question
):
    scan_id = await new_scan(store, redis)
    services, _ = services_for(
        store, redis, http, flow_settings, StaticEngine(result, stages=False)
    )

    await run_scan(services, scan_id, 1)

    scan = await the_scan(store, scan_id)
    assert (scan.status, scan.outcome, scan.clarification_question) == (
        ScanStatus.DONE,
        outcome,
        question,
    )


async def test_a_scan_that_runs_too_long_is_stopped(store, redis, http, make_settings):
    class Slow:
        async def propose(self, request, on_stage=None):
            await asyncio.sleep(5)

    scan_id = await new_scan(store, redis)
    settings = make_settings(scan_job_timeout_seconds=0.2)
    services, _ = services_for(store, redis, http, settings, Slow())

    await run_scan(services, scan_id, 1)

    assert (await the_scan(store, scan_id)).error_code == "SCAN_TIMEOUT"


async def test_a_result_of_a_run_that_was_replaced_meanwhile_is_dropped(
    store, redis, http, flow_settings
):
    scan_id = await new_scan(store, redis)

    class Replaced:
        async def propose(self, request, on_stage=None):
            async with store() as db:
                await db.execute(update(Scan).where(Scan.id == scan_id).values(run=2))
                await db.commit()
            return EngineResult(status=EngineStatus.OK, insights=[proposed()])

    services, _ = services_for(store, redis, http, flow_settings, Replaced())

    await run_scan(services, scan_id, 1)

    scan = await the_scan(store, scan_id)
    assert (scan.run, scan.status) == (2, ScanStatus.RUNNING)
    async with store() as db:
        assert (await db.scalars(select(Insight).where(Insight.scan_id == scan_id))).all() == []
        stages = (await db.scalars(select(ScanEvent).where(ScanEvent.scan_id == scan_id))).all()
    assert ("save", "skipped", "superseded") in {(e.stage, e.status, e.code) for e in stages}


async def test_a_new_run_reuses_the_scene_and_keeps_completed_insights(
    store, redis, http, flow_settings
):
    from src import clock

    scan_id = await new_scan(store, redis)
    first, _ = services_for(store, redis, http, flow_settings, DemoEngine())
    await run_scan(first, scan_id, 1)
    async with store() as db:
        kept = (await db.scalars(select(Insight).where(Insight.scan_id == scan_id))).one()
        kept.completed_at = clock.utcnow()
        await db.execute(
            update(Scan)
            .where(Scan.id == scan_id)
            .values(
                run=2,
                status=ScanStatus.QUEUED,
                focus={"box": {"x": 0, "y": 0, "width": 0.5, "height": 0.5}, "label": "ورقة"},
            )
        )
        await db.commit()
    engine = StaticEngine(
        EngineResult(status=EngineStatus.OK, insights=[proposed(entity_ids=["u1"])])
    )
    again, model = services_for(store, redis, http, flow_settings, engine, answers=[])

    await run_scan(again, scan_id, 2)

    assert model.calls == []
    request = engine.requests[0]
    assert request.focus_entity_id == "u1"
    assert request.scene.entities[-1].label_arabic == "ورقة"
    async with store() as db:
        rows = (
            await db.scalars(
                select(Insight).where(Insight.scan_id == scan_id).order_by(Insight.run)
            )
        ).all()
    assert [(row.run, row.completed_at is not None) for row in rows] == [(1, True), (2, False)]
    assert rows[1].anchor == {"x": 0.0, "y": 0.0, "width": 0.5, "height": 0.5}


def test_the_focus_names_a_thing_or_adds_the_drawn_box():
    base = scene(entity("e1"))

    assert apply_focus(base, None) == (base, None)
    assert apply_focus(base, {"entity_id": "e1"}) == (base, "e1")
    drawn, focus = apply_focus(
        base, {"box": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2}, "label": None}
    )
    assert focus == "u1"
    assert drawn.entities[-1].label_arabic == workflow.USER_SELECTION_LABEL
    assert drawn.entities[-1].bbox == BBox(x=0.1, y=0.1, width=0.2, height=0.2)
    twice, _ = apply_focus(drawn, {"box": {"x": 0.3, "y": 0.3, "width": 0.2, "height": 0.2}})
    assert [item.id for item in twice.entities] == ["e1", "u1"]


def test_call_records_become_rows_without_the_prompt_or_the_answer():
    from tests.fakes import make_record

    record = make_record().model_copy(
        update={"error_code": AiErrorCode.TIMEOUT, "retried_errors": (AiErrorCode.NETWORK,)}
    )
    row = workflow.call_rows([record], insight_id=1)[0]

    assert (row.provider, row.stage, row.kind, row.error_code) == (
        "ovh",
        "vision",
        "chat",
        "timeout",
    )
    assert row.retried_errors == ["network"]
    assert row.insight_id == 1
    assert row.input_tokens == 1000
