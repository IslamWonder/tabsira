"""
One placepix photo through the real scan pipeline of apps/api, as a member's scan runs it.

The steps and their order are the scan workflow's (`src/scans/workflow.py`): the image check,
the detector, the scene analysis with the provider's image moderation beside it, the scene's
words against the scripture guard and the store, then the insight engine (planner, retrieval,
the evidence gate, the composer) and the server's own acceptance of what it proposed. The
learner is a member who just signed up: nothing shared, nothing seen.

Nothing is written. Each run holds one database connection inside a transaction that is
rolled back at the end, and every session of the run joins it through a savepoint, so what
the engine records on the way (unresolved labels, unknown concepts, ruling demand) never
lands in the development database. Redis, the scan rows and the photo store are not used.

The outcome is the first accepted insight in the importer's shape (`InsightBodyIn` of
`src/cli/import_mock.py`): evidence by reference only, never a verse or a hadith text.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker
from src.ai.client import ModelClient
from src.ai.errors import AiCallError
from src.ai.records import CallLog, CallRecord
from src.cli.import_mock import InsightBodyIn
from src.config import Settings
from src.pipeline.engine import (
    EngineRequest,
    EngineStatus,
    EvidenceRef,
    InsightEngine,
    LearnerContext,
    ProposedInsight,
    QuranRef,
)
from src.pipeline.image_validator import ImageRejectedError, validate_image
from src.pipeline.leak_guard import ScriptureLeakError
from src.pipeline.person_words import PERSON_EN, PERSONS_EN
from src.pipeline.scene_analyzer import PERSON_DESCRIPTOR_NOTE, analyze_scene, scene_texts
from src.pipeline.schemas import (
    DetectorRequest,
    DetectorResult,
    ImageUpload,
    SceneAnalysis,
    SceneRequest,
)
from src.pipeline.sensitivity import moderate, with_moderation
from src.scans.accept import accept
from src.scans.workflow import VISION_FAILURES
from src.scripture.overlap import repeats_store

# The outcome kept; every other one drops the photo.
KEPT = "insights"
# Outcomes worth another attempt: the provider or the store did not answer.
TRANSIENT = frozenset({"model_unavailable", "source_unavailable"})

# The neutral words the scene stage writes for anyone it sees («شخص», «أشخاص»), with the
# article and the one-letter prefixes a word may carry. «الناس» (people at large) is not here:
# an insight speaks of people in general without anyone being in the photo.
_PERSON_WORDS = frozenset({"شخص", "أشخاص", "اشخاص", "شخصان", "شخصين"})
_PREFIXES = ("وبال", "وال", "فال", "بال", "كال", "ولل", "لل", "ال", "و", "ف", "ب", "ل", "ك", "")
_MARKS = re.compile("[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]")
_WORD = re.compile("[\u0621-\u064a\u0660-\u06ffA-Za-z]+")


class Detector(Protocol):
    async def detect(self, request: DetectorRequest) -> DetectorResult: ...


@dataclass(frozen=True)
class ScanTools:
    """What a run uses: built once for the whole processing, or by a test."""

    settings: Settings
    engine: AsyncEngine
    detector: Detector
    # The provider client of one run, recording its calls into the given log.
    client_factory: Callable[[CallLog], ModelClient]
    # The insight engine of one run, on that run's client and sessions.
    engine_factory: Callable[[ModelClient, async_sessionmaker[AsyncSession]], InsightEngine]


@dataclass
class ScanResult:
    """What became of one photo: the outcome, the insight when kept, and the calls it cost."""

    outcome: str
    body: dict[str, Any] | None = None
    calls: list[CallRecord] = field(default_factory=list)
    detector: bool = False
    # A short code saying what failed, never a text a model wrote.
    detail: str | None = None

    @property
    def transient(self) -> bool:
        return self.outcome in TRANSIENT


@contextlib.asynccontextmanager
async def rolled_back(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Yield sessions that share one transaction, which is rolled back whatever happens."""
    async with engine.connect() as connection:
        outer = await connection.begin()
        try:
            yield _sessions(connection)
        finally:
            await outer.rollback()


def _sessions(connection: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )


def mentions_people(scene: SceneAnalysis, body: dict[str, Any] | None = None) -> bool:
    """
    Tell whether the scene or the insight speaks of someone in the photo.

    A person entity, a person word the scene stage had to replace, or the neutral words for a
    person in what was seen: the scene's own texts, the insight's visible clues and its «seen»
    part.
    """
    if any(entity.label in {PERSON_EN, PERSONS_EN} for entity in scene.entities):
        return True
    if any(PERSON_DESCRIPTOR_NOTE in line for line in scene.rejected):
        return True
    texts = list(scene_texts(scene).values())
    if body is not None:
        texts += body["clues"]
        texts += [part["text"] for part in body["explanation"] if part["section"] == "seen"]
    return any(_names_person(text) for text in texts)


def _names_person(text: str) -> bool:
    for word in _WORD.findall(_MARKS.sub("", text)):
        if any(word.startswith(p) and word[len(p) :] in _PERSON_WORDS for p in _PREFIXES):
            return True
    return False


def body_of(insight: ProposedInsight) -> dict[str, Any]:
    """Return an accepted insight in the importer's shape, validated by the importer's model."""

    def evidence(ref: EvidenceRef | None) -> dict[str, Any] | None:
        if ref is None:
            return None
        why = {"matched_on": ref.matched_on, "relation": ref.relation.value}
        pointer = ref.ref
        if isinstance(pointer, QuranRef):
            return {"surah": pointer.surah, "ayah": pointer.ayah, **why}
        return {"collection": pointer.collection, "number": pointer.number, **why}

    step = insight.small_step
    raw = {
        "title": insight.title,
        "glimpse": insight.glimpse,
        "concept": insight.why.concept,
        "relation": insight.relation.value,
        "clues": list(insight.why.visible_clues),
        "limits": list(insight.why.limits),
        "entity_ids": list(insight.entity_ids),
        "quran": evidence(insight.quran),
        "hadith": evidence(insight.hadith),
        "explanation": [{"section": p.section, "text": p.text} for p in insight.explanation],
        "small_step": (
            {"text": step.text, "kind": step.kind, "grounded_in": list(step.grounded_in)}
            if step
            else None
        ),
    }
    return InsightBodyIn.model_validate(raw).model_dump(mode="json")


async def run_scan(tools: ScanTools, photo: bytes, scan_id: str) -> ScanResult:
    """Run one photo through the pipeline; never raises for what a member's scan survives."""
    settings = tools.settings
    try:
        validated = validate_image(
            ImageUpload(data=photo),
            max_bytes=settings.image_max_bytes,
            max_pixels=settings.image_max_pixels,
        )
    except ImageRejectedError as rejected:
        return ScanResult("image_rejected", detail=rejected.code.value)
    log = CallLog()
    client = tools.client_factory(log)
    result = ScanResult("model_unavailable")
    try:
        async with rolled_back(tools.engine) as sessions:
            result = await _scan(tools, client, sessions, validated.model_image, scan_id, result)
    except AiCallError as error:
        result.outcome, result.detail = "model_unavailable", error.code.value
    except (SQLAlchemyError, OSError) as error:
        result.outcome, result.detail = "source_unavailable", type(error).__name__
    result.calls = list(log.records)
    return result


async def _scan(
    tools: ScanTools,
    client: ModelClient,
    sessions: async_sessionmaker[AsyncSession],
    image: Any,
    scan_id: str,
    result: ScanResult,
) -> ScanResult:
    scene = await _understand(tools, client, sessions, image, result)
    if scene is None:
        return result
    if scene.is_sensitive:
        result.outcome = "sensitive"
        return result
    if mentions_people(scene):
        result.outcome = "people"
        return result
    engine = tools.engine_factory(client, sessions)
    proposed = await engine.propose(
        EngineRequest(scan_id=scan_id, scene=scene, learner=LearnerContext())
    )
    if proposed.status in {EngineStatus.SOURCE_UNAVAILABLE, EngineStatus.MODEL_UNAVAILABLE}:
        result.outcome = proposed.status.value
        return result
    async with sessions() as db:
        accepted = await accept(
            db, scene, proposed.insights if proposed.status is EngineStatus.OK else []
        )
    if not accepted.insights:
        result.outcome = (
            "needs_clarification"
            if proposed.status is EngineStatus.NEEDS_CLARIFICATION
            else "no_relevant_evidence"
        )
        result.detail = ",".join(sorted(set(accepted.refusals))) or None
        return result
    body = body_of(accepted.insights[0])
    result.outcome = "people" if mentions_people(scene, body) else KEPT
    result.body = body if result.outcome == KEPT else None
    return result


async def _understand(
    tools: ScanTools,
    client: ModelClient,
    sessions: async_sessionmaker[AsyncSession],
    image: Any,
    result: ScanResult,
) -> SceneAnalysis | None:
    """Detect, describe and moderate as the workflow does; None when the photo stops here."""
    moderation = asyncio.create_task(moderate(image, client=client))
    try:
        detected = await tools.detector.detect(DetectorRequest(image=image))
        result.detector = detected.available
        scene = await analyze_scene(SceneRequest(image=image, detector=detected), client=client)
        verdict = await moderation
    except AiCallError as error:
        result.outcome = "vision_failed" if error.code in VISION_FAILURES else "model_unavailable"
        result.detail = error.code.value
        return None
    except ScriptureLeakError:
        result.outcome, result.detail = "vision_failed", "leak"
        return None
    finally:
        if not moderation.done():
            moderation.cancel()
            with contextlib.suppress(BaseException):
                await moderation
    scene = with_moderation(scene, verdict)
    async with sessions() as db:
        copied = await repeats_store(db, scene_texts(scene).values())
    if copied:
        result.outcome, result.detail = "vision_failed", "leak"
        return None
    return scene
