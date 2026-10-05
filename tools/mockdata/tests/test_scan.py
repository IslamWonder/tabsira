from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError
from src.ai.records import CallLog
from src.config import AiStage
from src.pipeline.engine import EngineRequest, EngineResult, EngineStatus, ProposedInsight
from src.pipeline.leak_guard import ScriptureLeakError
from src.pipeline.scene_analyzer import PERSON_DESCRIPTOR_NOTE
from src.pipeline.schemas import DetectorRequest, DetectorResult, SceneAnalysis
from src.pipeline.sensitivity import Moderation
from src.scans.accept import Accepted

from mockdata import scan
from mockdata.scan import ScanResult, ScanTools, body_of, mentions_people, rolled_back, run_scan

from .fakes import FakeClient, entity, failure, insight, jpeg, settings
from .fakes import scene as make_scene


class Empty(BaseModel):
    pass


# ─── rolled_back ───


class FakeTransaction:
    def __init__(self) -> None:
        self.rolled_back = False

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeConnection:
    def __init__(self) -> None:
        self.transaction = FakeTransaction()

    async def begin(self) -> FakeTransaction:
        return self.transaction


class FakeEngine:
    def __init__(self) -> None:
        self.connection = FakeConnection()

    @contextlib.asynccontextmanager
    async def connect(self) -> AsyncIterator[FakeConnection]:
        yield self.connection


async def test_rolled_back_joins_by_savepoint_and_rolls_back_even_on_error() -> None:
    engine = FakeEngine()
    with pytest.raises(RuntimeError):
        async with rolled_back(engine) as sessions:  # type: ignore[arg-type]
            assert sessions.kw["join_transaction_mode"] == "create_savepoint"
            assert sessions.kw["bind"] is engine.connection
            raise RuntimeError
    assert engine.connection.transaction.rolled_back


# ─── mentions_people ───


def test_a_person_entity_mentions_people() -> None:
    assert mentions_people(make_scene(entities=[entity("person", "شخص")]))
    assert mentions_people(make_scene(entities=[entity("people", "مجموعة")]))


def test_a_replaced_person_word_mentions_people() -> None:
    note = f"description: {PERSON_DESCRIPTOR_NOTE}«شخص»: رجل"
    assert mentions_people(make_scene(rejected=[note]))


def test_the_neutral_words_with_their_prefixes_mention_people() -> None:
    assert mentions_people(make_scene(description="قطة بجانب الشخص"))
    assert mentions_people(make_scene(description="وأشخاصٌ قرب الباب"))
    assert mentions_people(make_scene(description="شخصان يمشيان."))


def test_personal_and_people_at_large_do_not() -> None:
    assert not mentions_people(make_scene(description="خطوة شخصية، والناس في السوق بعيدا"))


def test_the_insight_clues_and_seen_part_count_but_not_its_other_parts() -> None:
    clean = make_scene()
    assert mentions_people(clean, body_of(insight(clues=["شخص يطعم قطة"])))
    assert mentions_people(clean, body_of(insight(seen="أشخاص حول القطة")))
    body = body_of(insight())
    body["explanation"][1]["text"] = "كل شخص مسؤول"
    assert not mentions_people(clean, body)


# ─── body_of ───


def test_body_of_keeps_references_and_the_composed_text() -> None:
    body = body_of(insight())
    assert body["quran"] == {
        "surah": 2,
        "ayah": 164,
        "collection": None,
        "number": None,
        "matched_on": "التفكر",
        "relation": "close_conceptual",
    }
    assert body["hadith"]["collection"] == "bukhari"
    assert body["hadith"]["number"] == "1"
    assert body["hadith"]["relation"] == "thematic_reminder"
    assert body["concept"] == "الرفق"
    assert body["clues"] == ["قطة"]
    assert body["limits"] == ["لا نعرف صاحبها"]
    assert body["entity_ids"] == ["e1"]
    assert body["small_step"] == {"text": "أطعم قطة اليوم", "kind": "reflection", "grounded_in": []}
    assert [part["section"] for part in body["explanation"]] == ["seen", "value"]


def test_body_of_without_evidence_or_step() -> None:
    body = body_of(insight(quran=False, hadith=False, step=False))
    assert body["quran"] is None
    assert body["hadith"] is None
    assert body["small_step"] is None


# ─── run_scan ───


class FakeDetector:
    def __init__(self) -> None:
        self.requests: list[DetectorRequest] = []

    async def detect(self, request: DetectorRequest) -> DetectorResult:
        self.requests.append(request)
        return DetectorResult(available=True, latency_ms=1)


class FakeEngineRun:
    def __init__(self, result: EngineResult | Exception) -> None:
        self.result = result
        self.requests: list[EngineRequest] = []

    async def propose(self, request: EngineRequest, on_stage: Any = None) -> EngineResult:
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class Setup:
    """The patched pipeline of one test: what the scene, the store and the gate answer."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.scene: SceneAnalysis | Exception = make_scene()
        self.copied = False
        self.accepted = Accepted(insights=[insight()])
        self.engine = FakeEngineRun(EngineResult(status=EngineStatus.OK, insights=[insight()]))
        self.detector = FakeDetector()
        self.client = FakeClient()
        self.accepted_from: list[list[ProposedInsight]] = []

        @contextlib.asynccontextmanager
        async def fake_rolled_back(_engine: object) -> AsyncIterator[Callable[[], Any]]:
            @contextlib.asynccontextmanager
            async def session() -> AsyncIterator[object]:
                yield object()

            yield session

        async def analyze(request: object, *, client: object) -> SceneAnalysis:
            if isinstance(self.scene, Exception):
                raise self.scene
            return self.scene

        async def repeats(db: object, texts: object) -> bool:
            return self.copied

        async def accept(db: object, scene: object, proposed: list[ProposedInsight]) -> Accepted:
            self.accepted_from.append(list(proposed))
            return self.accepted

        monkeypatch.setattr(scan, "rolled_back", fake_rolled_back)
        monkeypatch.setattr(scan, "analyze_scene", analyze)
        monkeypatch.setattr(scan, "repeats_store", repeats)
        monkeypatch.setattr(scan, "accept", accept)

    def tools(self) -> ScanTools:
        def client_factory(log: CallLog) -> FakeClient:
            self.client.log = log
            return self.client

        return ScanTools(
            settings=settings(),
            engine=object(),  # type: ignore[arg-type]
            detector=self.detector,
            client_factory=client_factory,
            engine_factory=lambda client, sessions: self.engine,
        )


@pytest.fixture
def setup(monkeypatch: pytest.MonkeyPatch) -> Setup:
    return Setup(monkeypatch)


async def test_a_photo_with_insights_is_kept_with_the_first_accepted_one(setup: Setup) -> None:
    result = await run_scan(setup.tools(), jpeg(), "mock-1")
    assert result.outcome == "insights"
    assert not result.transient
    assert result.detector
    assert result.body is not None
    assert result.body["title"] == "سكينة القطة"
    request = setup.engine.requests[0]
    assert request.scan_id == "mock-1"
    assert request.learner.seen_quran == []
    assert setup.detector.requests[0].image.width == 64


async def test_a_photo_that_is_not_an_image_is_rejected(setup: Setup) -> None:
    result = await run_scan(setup.tools(), b"not a photo", "mock-1")
    assert (result.outcome, result.detail) == ("image_rejected", "unsupported_media_type")


@pytest.mark.parametrize(
    ("error", "outcome", "detail"),
    [
        (failure("invalid_output"), "vision_failed", "invalid_output"),
        (failure("timeout"), "model_unavailable", "timeout"),
        (ScriptureLeakError({}), "vision_failed", "leak"),
    ],
)
async def test_a_failed_scene_stops_the_photo(
    setup: Setup, error: Exception, outcome: str, detail: str
) -> None:
    setup.scene = error
    result = await run_scan(setup.tools(), jpeg(), "mock-1")
    assert (result.outcome, result.detail) == (outcome, detail)
    assert setup.engine.requests == []


async def test_scene_words_that_repeat_the_store_stop_the_photo(setup: Setup) -> None:
    setup.copied = True
    result = await run_scan(setup.tools(), jpeg(), "mock-1")
    assert (result.outcome, result.detail) == ("vision_failed", "leak")


async def test_a_sensitive_scene_is_dropped_before_the_engine(setup: Setup) -> None:
    setup.scene = make_scene(sensitive=True)
    result = await run_scan(setup.tools(), jpeg(), "mock-1")
    assert result.outcome == "sensitive"
    assert setup.engine.requests == []


async def test_a_scene_with_people_is_dropped_before_the_engine(setup: Setup) -> None:
    setup.scene = make_scene(entities=[entity("person", "شخص")])
    result = await run_scan(setup.tools(), jpeg(), "mock-1")
    assert result.outcome == "people"
    assert setup.engine.requests == []


async def test_an_insight_that_speaks_of_people_is_dropped(setup: Setup) -> None:
    setup.accepted = Accepted(insights=[insight(clues=["شخص"])])
    result = await run_scan(setup.tools(), jpeg(), "mock-1")
    assert result.outcome == "people"
    assert result.body is None


@pytest.mark.parametrize(
    "status", [EngineStatus.SOURCE_UNAVAILABLE, EngineStatus.MODEL_UNAVAILABLE]
)
async def test_an_engine_that_could_not_work_is_worth_a_retry(
    setup: Setup, status: EngineStatus
) -> None:
    setup.engine = FakeEngineRun(EngineResult(status=status))
    result = await run_scan(setup.tools(), jpeg(), "mock-1")
    assert result.outcome == status.value
    assert result.transient


async def test_a_question_is_not_an_insight(setup: Setup) -> None:
    setup.engine = FakeEngineRun(
        EngineResult(status=EngineStatus.NEEDS_CLARIFICATION, clarification_question="ما هذا؟")
    )
    setup.accepted = Accepted(insights=[])
    result = await run_scan(setup.tools(), jpeg(), "mock-1")
    assert (result.outcome, result.detail) == ("needs_clarification", None)
    assert setup.accepted_from == [[]]


async def test_nothing_accepted_is_no_relevant_evidence_with_the_refusals(setup: Setup) -> None:
    setup.accepted = Accepted(insights=[], refusals=["leak", "no_evidence", "leak"])
    result = await run_scan(setup.tools(), jpeg(), "mock-1")
    assert (result.outcome, result.detail) == ("no_relevant_evidence", "leak,no_evidence")


async def test_a_model_error_inside_the_engine_is_worth_a_retry(setup: Setup) -> None:
    setup.engine = FakeEngineRun(failure("rate_limited"))
    result = await run_scan(setup.tools(), jpeg(), "mock-1")
    assert (result.outcome, result.detail) == ("model_unavailable", "rate_limited")


@pytest.mark.parametrize(
    ("error", "detail"),
    [(OperationalError("x", {}, Exception()), "OperationalError"), (OSError(), "OSError")],
)
async def test_a_store_that_fails_is_worth_a_retry(
    setup: Setup, error: Exception, detail: str
) -> None:
    setup.engine = FakeEngineRun(error)
    result = await run_scan(setup.tools(), jpeg(), "mock-1")
    assert (result.outcome, result.detail) == ("source_unavailable", detail)


async def test_the_calls_of_the_run_are_returned(
    setup: Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup.client.answers = [{}]

    async def analyze(request: object, *, client: FakeClient) -> SceneAnalysis:
        await client.chat_json(Empty, stage=AiStage.VISION, system="", user="")
        return make_scene()

    monkeypatch.setattr(scan, "analyze_scene", analyze)
    result = await run_scan(setup.tools(), jpeg(), "mock-1")
    assert len(result.calls) == 1


async def test_the_moderation_is_stopped_when_the_scene_fails(
    setup: Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = asyncio.Event()

    async def slow(image: object, *, client: object) -> Moderation:
        started.set()
        await asyncio.sleep(3600)
        raise AssertionError  # pragma: no cover - cancelled before

    async def analyze(request: object, *, client: object) -> SceneAnalysis:
        await started.wait()
        raise failure("timeout")

    monkeypatch.setattr(scan, "moderate", slow)
    monkeypatch.setattr(scan, "analyze_scene", analyze)
    result = await run_scan(setup.tools(), jpeg(), "mock-1")
    assert result.outcome == "model_unavailable"


def test_transient_outcomes() -> None:
    assert ScanResult("model_unavailable").transient
    assert ScanResult("source_unavailable").transient
    assert not ScanResult("people").transient
