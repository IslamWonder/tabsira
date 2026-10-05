"""
The scan job: detector, scene, sensitivity, then the engine, with honest progress.

One job runs one run of one scan, and running it twice changes nothing:

- a Redis lock keeps two workers off the same scan at once;
- the job claims the scan only while it is queued (or running, after a crash)
  for the same run; a job of an earlier run, or of a finished one, does nothing;
- before saving, the run is read again under a row lock, so a focus or a
  clarification asked meanwhile wins and the stale result is dropped;
- saving replaces the insights of the scan that were not completed, so a job
  that died after saving and runs again saves the same thing once.

The photo comes from the temporary store; a sensitive scene's photo is deleted
the moment the verdict is known, and the model copy when the scene is built.
Every model call is recorded in `ai_calls` and every stage in `scan_events`,
whatever the outcome.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
from PIL import Image
from redis.asyncio import Redis
from sqlalchemy import delete, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src import clock
from src.ai.client import ModelClient
from src.ai.errors import AiCallError, AiErrorCode
from src.ai.records import CallLog, CallRecord
from src.config import Settings
from src.errors import ErrorCode
from src.models import AiCall, Insight, InsightOrigin, Scan, ScanEvent, ScanOutcome, ScanStatus
from src.owner import Owner
from src.pipeline.engine import (
    EngineRequest,
    EngineResult,
    EngineStage,
    EngineStatus,
    ProposedInsight,
)
from src.pipeline.leak_guard import LeakGuard, ScriptureLeakError
from src.pipeline.scene_analyzer import analyze_scene, scene_texts
from src.pipeline.schemas import (
    DetectorRequest,
    DetectorResult,
    EncodedImage,
    EntityOrigin,
    EvidenceStatus,
    SceneAnalysis,
    SceneEntity,
    SceneRequest,
)
from src.pipeline.sensitivity import Moderation, moderate, with_moderation
from src.scans import buffer, progress
from src.scans.accept import accept
from src.scans.engines import EngineDeps, EngineFactory
from src.scans.sound import candidate_entities, first_stored
from src.scripture.overlap import repeats_store
from src.services.learner_service import learner_context
from src.storage.sounds import SoundStore

log = logging.getLogger("tabsira.scans.workflow")

# Codes a vision failure is reported with: the model answered, but not usefully.
VISION_FAILURES = frozenset(
    {AiErrorCode.INVALID_OUTPUT, AiErrorCode.REFUSED, AiErrorCode.TRUNCATED}
)
USER_SELECTION_ID = "u1"
USER_SELECTION_LABEL = "ما حدّدته"


class Detector(Protocol):
    async def detect(  # pragma: no cover - a protocol declares the call; DetectorClient is tested
        self, request: DetectorRequest
    ) -> DetectorResult: ...


@dataclass(frozen=True)
class ScanServices:
    """What a job needs, built once per worker (or by a test)."""

    settings: Settings
    sessionmaker: async_sessionmaker[AsyncSession]
    redis: Redis
    http: httpx.AsyncClient
    # Builds the provider client of one run, writing its calls to the given log.
    client_factory: Callable[[CallLog], ModelClient]
    engine_factory: EngineFactory
    detector: Detector
    timer: Callable[[], float] = time.perf_counter
    # The ontology's sounds; without a store no scan announces one.
    sounds: SoundStore | None = None


class ScanFailedError(Exception):
    """A run that cannot give a result; `code` is what the reader is told."""

    def __init__(self, code: ErrorCode, detail: str) -> None:
        super().__init__(f"{code.value}: {detail}")
        self.code = code


@dataclass
class Trace:
    """The stage timings of one run, saved with the run whatever happens."""

    timer: Callable[[], float]
    events: list[ScanEvent] = field(default_factory=list)

    def add(self, stage: str, status: str, started: float, code: str | None = None) -> None:
        self.events.append(
            ScanEvent(
                at=clock.utcnow(),
                stage=stage,
                status=status,
                ms=round((self.timer() - started) * 1000),
                code=code,
            )
        )


@dataclass
class Run:
    services: ScanServices
    scan_id: int
    run: int
    owner: Owner
    calls: CallLog = field(default_factory=CallLog)
    trace: Trace = field(init=False)

    def __post_init__(self) -> None:
        self.trace = Trace(self.services.timer)

    async def publish(self, event: str, data: dict[str, Any]) -> None:
        await progress.publish(
            self.services.redis,
            self.scan_id,
            event,
            {"run": self.run, **data},
            ttl=self.services.settings.scan_events_ttl_seconds,
        )

    async def stage(self, stage: EngineStage, state: str) -> None:
        await self.publish("stage", {"stage": stage.value, "state": state})


def lock_key(scan_id: int) -> str:
    return f"scan:{scan_id}:lock"


async def run_scan(services: ScanServices, scan_id: int, run: int) -> None:
    """Run one run of a scan once, whoever else was asked to run it."""
    lock_seconds = int(services.settings.scan_job_timeout_seconds) + 60
    if not await services.redis.set(lock_key(scan_id), run, nx=True, ex=lock_seconds):
        log.info("scan %s run %s is already being run", scan_id, run)
        return
    try:
        owner = await _claim(services.sessionmaker, scan_id, run)
        if owner is not None:
            await _execute(Run(services, scan_id, run, owner))
    finally:
        await services.redis.delete(lock_key(scan_id))


async def _claim(
    sessionmaker: async_sessionmaker[AsyncSession], scan_id: int, run: int
) -> Owner | None:
    async with sessionmaker() as db:
        row = (
            await db.execute(
                update(Scan)
                .where(
                    Scan.id == scan_id,
                    Scan.run == run,
                    Scan.status.in_([ScanStatus.QUEUED, ScanStatus.RUNNING]),
                )
                .values(status=ScanStatus.RUNNING)
                .returning(Scan.user_id, Scan.guest_key)
            )
        ).one_or_none()
        await db.commit()
    if row is None:
        return None
    return Owner(user_id=row.user_id, guest_key=row.guest_key)


async def _execute(job: Run) -> None:
    services = job.services
    started = services.timer()
    try:
        async with asyncio.timeout(services.settings.scan_job_timeout_seconds):
            outcome = await _analyse_and_propose(job)
    except ScanFailedError as failure:
        await _fail(job, failure.code, started)
    except TimeoutError:
        await _fail(job, ErrorCode.SCAN_TIMEOUT, started)
    except Exception:
        log.exception("scan %s run %s failed", job.scan_id, job.run)
        await _fail(job, ErrorCode.INTERNAL_ERROR, started)
    else:
        job.trace.add("job", "done", started, outcome)
    finally:
        await _save_trace(job)


async def _fail(job: Run, code: ErrorCode, started: float) -> None:
    job.trace.add("job", "failed", started, code.value)
    async with job.services.sessionmaker() as db:
        await db.execute(
            update(Scan)
            .where(Scan.id == job.scan_id, Scan.run == job.run)
            .values(status=ScanStatus.FAILED, error_code=code.value, finished_at=clock.utcnow())
        )
        understood = await db.scalar(select(Scan.scene.is_not(None)).where(Scan.id == job.scan_id))
        await db.commit()
    # Without a sensitivity verdict the photo is never shown, so nothing of it is kept.
    copies = (buffer.Copy.MODEL,) if understood else tuple(buffer.Copy)
    await buffer.drop(job.services.redis, job.scan_id, *copies)
    await job.publish("failed", {"code": code.value})


async def _save_trace(job: Run) -> None:
    async with job.services.sessionmaker() as db:
        for event in job.trace.events:
            event.scan_id, event.run = job.scan_id, job.run
            db.add(event)
        db.add_all(call_rows(job.calls.records, scan_id=job.scan_id))
        await db.commit()


def call_rows(
    records: list[CallRecord],
    *,
    scan_id: int | None = None,
    insight_id: int | None = None,
) -> list[AiCall]:
    """Return the `ai_calls` rows of some call records."""
    return [
        AiCall(
            at=record.started_at,
            scan_id=scan_id,
            insight_id=insight_id,
            provider=record.provider.value,
            model=record.model,
            stage=record.stage.value,
            kind=record.kind.value,
            attempts=record.attempts,
            input_tokens=record.usage.input_tokens,
            output_tokens=record.usage.output_tokens,
            reasoning_tokens=record.usage.reasoning_tokens,
            cached_input_tokens=record.usage.cached_input_tokens,
            cost_usd=record.cost_usd,
            latency_ms=record.latency_ms,
            ok=record.ok,
            error_code=record.error_code.value if record.error_code else None,
            finish_reason=record.finish_reason,
            retried_errors=[code.value for code in record.retried_errors],
        )
        for record in records
    ]


async def _analyse_and_propose(job: Run) -> str:
    services = job.services
    client = services.client_factory(job.calls)
    async with services.sessionmaker() as db:
        scan = await db.get(Scan, job.scan_id)
        stored_scene = scan.scene if scan is not None else None
        focus = dict(scan.focus) if scan is not None and scan.focus else None
        answer = scan.clarification_answer if scan is not None else None
    await job.stage(EngineStage.UNDERSTANDING, "started")
    if stored_scene is None:
        scene = await _understand(job, client)
    else:
        scene = SceneAnalysis.model_validate(stored_scene)
    await job.stage(EngineStage.UNDERSTANDING, "done")

    scene, focus_id = apply_focus(scene, focus)
    await _announce_sound(job, scene, focus_id, clarified=answer is not None)
    async with services.sessionmaker() as db:
        learner = await learner_context(db, job.owner)
    engine = services.engine_factory(
        EngineDeps(services.settings, client, services.sessionmaker, services.http)
    )
    request = EngineRequest(
        scan_id=str(job.scan_id),
        scene=scene,
        focus_entity_id=focus_id,
        clarification_answer=answer,
        learner=learner,
    )
    current: list[EngineStage] = []

    async def on_stage(stage: EngineStage) -> None:
        if current:
            await job.stage(current[-1], "done")
        current.append(stage)
        await job.stage(stage, "started")

    try:
        result = await engine.propose(request, on_stage)
    except AiCallError as error:
        raise ScanFailedError(ErrorCode.MODEL_UNAVAILABLE, error.code.value) from None
    if current:
        await job.stage(current[-1], "done")
    for stage, ms in result.stage_ms.items():
        job.trace.events.append(
            ScanEvent(at=clock.utcnow(), stage=stage.value, status="done", ms=ms)
        )
    return await _conclude(job, scene, result)


async def _announce_sound(
    job: Run, scene: SceneAnalysis, focus_id: str | None, *, clarified: bool
) -> None:
    """Publish the scene's sound while the engine works; a sound never stops a scan."""
    store = job.services.sounds
    if store is None:
        return
    try:
        async with job.services.sessionmaker() as db:
            entity_ids = await candidate_entities(db, scene, focus_id=focus_id, clarified=clarified)
    except SQLAlchemyError:
        log.warning("scan %s: the scene's sound was not looked up", job.scan_id)
        return
    path = await first_stored(store, entity_ids)
    if path is not None:
        await job.publish("sound", {"url": path})


async def _understand(job: Run, client: ModelClient) -> SceneAnalysis:
    services = job.services
    data = await buffer.get(
        services.redis,
        job.scan_id,
        buffer.Copy.MODEL,
        key=buffer.photo_key(services.settings),
    )
    if data is None:
        raise ScanFailedError(ErrorCode.ASSET_MISSING, "the photo left the temporary store")
    with Image.open(io.BytesIO(data)) as decoded:
        width, height = decoded.size
    image = EncodedImage(data=data, width=width, height=height)
    # The moderation looks at the photo alone, so it runs while the scene is described;
    # its trace time runs from its start, overlapping the description.
    started = services.timer()
    moderation = asyncio.create_task(moderate(image, client=client))
    try:
        scene = await _describe(job, client, image)
    except BaseException:
        await _stop(moderation)
        raise
    scene = with_moderation(scene, await moderation)
    guard = scene.guard
    job.trace.add(
        "sensitivity",
        "done",
        started,
        guard.moderation_status.value if guard is not None else None,
    )
    if scene.is_sensitive:
        # Rule 8: the photo of a sensitive scene is never kept, not even for the hour.
        await buffer.drop(services.redis, job.scan_id)
    else:
        await buffer.drop(services.redis, job.scan_id, buffer.Copy.MODEL)
    async with services.sessionmaker() as db:
        await db.execute(
            update(Scan)
            .where(Scan.id == job.scan_id)
            .values(
                scene=scene.model_dump(mode="json"),
                sensitive=scene.is_sensitive,
                # The guard's verdict is the union of the model's flags and the moderation's.
                sensitive_categories=[
                    category.value for category in (guard.categories if guard else scene.sensitive)
                ],
            )
        )
        await db.commit()
    return scene


async def _stop(task: asyncio.Task[Moderation]) -> None:
    """Cancel the moderation of a scan that ended, and wait until it has stopped."""
    task.cancel()
    with contextlib.suppress(BaseException):
        await task


async def _describe(job: Run, client: ModelClient, image: EncodedImage) -> SceneAnalysis:
    """Detect, describe and check the scene's words; a failure ends the scan."""
    services = job.services
    started = services.timer()
    detected = await services.detector.detect(DetectorRequest(image=image))
    job.trace.add("detect", "done" if detected.available else "skipped", started, detected.error)

    started = services.timer()
    try:
        scene = await analyze_scene(SceneRequest(image=image, detector=detected), client=client)
    except AiCallError as error:
        code = (
            ErrorCode.VISION_FAILED
            if error.code in VISION_FAILURES
            else ErrorCode.MODEL_UNAVAILABLE
        )
        job.trace.add("understand", "failed", started, error.code.value)
        raise ScanFailedError(code, error.code.value) from None
    except ScriptureLeakError:
        job.trace.add("understand", "failed", started, "leak")
        raise ScanFailedError(ErrorCode.VISION_FAILED, "scripture-like text in the scene") from None
    async with services.sessionmaker() as db:
        # The scene's words are shown too: no run of a stored text in them, marked or not.
        copied = await repeats_store(db, scene_texts(scene).values())
    if copied:
        job.trace.add("understand", "failed", started, "leak")
        raise ScanFailedError(ErrorCode.VISION_FAILED, "scripture-like text in the scene")
    job.trace.add("understand", "done", started)
    return scene


def apply_focus(
    scene: SceneAnalysis, focus: dict[str, Any] | None
) -> tuple[SceneAnalysis, str | None]:
    """Return the scene the engine sees and the id it should focus on."""
    if not focus:
        return scene, None
    entity_id = focus.get("entity_id")
    if isinstance(entity_id, str):
        return scene, entity_id
    selection = SceneEntity(
        id=USER_SELECTION_ID,
        label=str(focus.get("label") or "selection"),
        label_arabic=str(focus.get("label") or USER_SELECTION_LABEL),
        bbox=focus["box"],
        origin=EntityOrigin.USER_SELECTION,
        status=EvidenceStatus.USER_CONFIRMED,
    )
    entities = [entity for entity in scene.entities if entity.id != USER_SELECTION_ID]
    return scene.model_copy(update={"entities": [*entities, selection]}), USER_SELECTION_ID


async def _conclude(job: Run, scene: SceneAnalysis, result: EngineResult) -> str:
    if result.status is EngineStatus.SOURCE_UNAVAILABLE:
        raise ScanFailedError(
            ErrorCode.SOURCE_UNAVAILABLE, "the engine could not reach the sources"
        )
    if result.status is EngineStatus.MODEL_UNAVAILABLE:
        raise ScanFailedError(ErrorCode.MODEL_UNAVAILABLE, "the engine could not reach a model")
    if result.status is EngineStatus.CORPUS_UNAVAILABLE:
        raise ScanFailedError(ErrorCode.CORPUS_UNAVAILABLE, "the store holds no searchable corpus")
    if result.status is EngineStatus.RETRIEVAL_ERROR:
        raise ScanFailedError(ErrorCode.RETRIEVAL_ERROR, "the search could not run")
    started = job.services.timer()
    async with job.services.sessionmaker() as db:
        accepted = await accept(
            db, scene, result.insights if result.status is EngineStatus.OK else []
        )
        question = await _question(db, result)
        if accepted.insights:
            outcome = ScanOutcome.INSIGHTS
        elif result.status is EngineStatus.NEEDS_CLARIFICATION and question:
            outcome = ScanOutcome.NEEDS_CLARIFICATION
        elif result.status is EngineStatus.INCOMPLETE_EVIDENCE_PAIR:
            outcome = ScanOutcome.INCOMPLETE_EVIDENCE_PAIR
        else:
            outcome = ScanOutcome.NO_RELEVANT_EVIDENCE
        ids = await _save(db, job, outcome, accepted.insights, question, result)
        if ids is None:
            await db.rollback()
            job.trace.add("save", "skipped", started, "superseded")
            return "superseded"
        await db.commit()
    for reason in accepted.refusals:
        job.trace.add("accept", "skipped", started, reason)
    job.trace.add("save", "done", started)
    await job.publish("done", {"outcome": outcome.value, "insight_ids": [str(i) for i in ids]})
    return outcome.value


async def _question(db: AsyncSession, result: EngineResult) -> str | None:
    """Return the engine's question to the learner, unless it carries scripture, marked or not."""
    question = (result.clarification_question or "").strip()
    if not question or LeakGuard().check(question).leaked or await repeats_store(db, [question]):
        return None
    return question


async def _save(
    db: AsyncSession,
    job: Run,
    outcome: ScanOutcome,
    insights: list[ProposedInsight],
    question: str | None,
    result: EngineResult,
) -> list[int] | None:
    """Save the run's result under a lock of the scan row; None when a newer run took over."""
    scan = await db.scalar(select(Scan).where(Scan.id == job.scan_id).with_for_update())
    if scan is None or scan.run != job.run:
        return None
    await db.execute(
        delete(Insight).where(Insight.scan_id == job.scan_id, Insight.completed_at.is_(None))
    )
    rows = [
        # The scan row's owner now: a guest who signed in meanwhile was merged into an account.
        insight_row(
            Owner(user_id=scan.user_id, guest_key=scan.guest_key),
            insight,
            scan=scan,
            position=position,
        )
        for position, insight in enumerate(insights)
    ]
    db.add_all(rows)
    scan.status = ScanStatus.DONE
    scan.outcome = outcome
    scan.error_code = None
    scan.finished_at = clock.utcnow()
    scan.clarification_question = question if outcome is ScanOutcome.NEEDS_CLARIFICATION else None
    scan.awaiting_ruling = [ref.model_dump(exclude={"kind"}) for ref in result.awaiting_ruling]
    scan.engine_trace = result.trace or None
    await db.flush()
    return [row.id for row in rows]


def insight_row(owner: Owner, insight: ProposedInsight, *, scan: Scan, position: int) -> Insight:
    """Return the row of a proposed insight, its evidence kept by reference."""
    quran, hadith = insight.quran, insight.hadith
    return Insight(
        **owner.columns(),
        scan_id=scan.id,
        origin=InsightOrigin.SCAN,
        run=scan.run,
        position=position,
        engine=scan.engine,
        title=insight.title,
        glimpse=insight.glimpse,
        entity_ids=insight.entity_ids,
        action_ids=insight.action_ids,
        anchor=insight.anchor.model_dump() if insight.anchor else None,
        relation=insight.relation.value,
        quran_surah=getattr(quran.ref, "surah", None) if quran else None,
        quran_ayah=getattr(quran.ref, "ayah", None) if quran else None,
        quran_evidence=quran.model_dump(mode="json", exclude={"ref"}) if quran else None,
        hadith_collection=getattr(hadith.ref, "collection", None) if hadith else None,
        hadith_number=getattr(hadith.ref, "number", None) if hadith else None,
        hadith_evidence=hadith.model_dump(mode="json", exclude={"ref"}) if hadith else None,
        explanation=[part.model_dump(mode="json") for part in insight.explanation],
        why=insight.why.model_dump(mode="json"),
        small_step=insight.small_step.model_dump(mode="json") if insight.small_step else None,
        learning_unit_id=insight.learning_unit_id,
        learning_path_version=insight.learning_path_version,
    )
