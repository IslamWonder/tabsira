"""
The engine evaluation (`make eval`): the whole scan pipeline on the gold scenes, checked by rule.

Each gold image goes through the image check, the detector (skipped, and said
so, when services/vision does not answer), the scene analysis, the
sensitivity guard and the insight engine, with the real providers. Then:

- scripture leakage: every text of every insight through the scripture guard
  (patterns, the whole Quran, the hadiths shown); must be 0;
- every evidence reference must name a stored text whose hash still matches
  its bytes; must be 100%;
- the relation types used, and whether the hoped-for texts came up;
- abstention: a scene that should abstain gets a question or no insight, and
  a scene that should not, gets an insight;
- p50 and p95 of each stage, and the cost of a scan.
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.client import ModelClient
from src.ai.errors import AiCallError
from src.ai.records import CallLog
from src.evaluation.benchmark import PreparedScene
from src.models import Hadith, QuranVerse
from src.pipeline.engine import (
    EngineRequest,
    EngineResult,
    EngineStatus,
    HadithRef,
    InsightEngine,
    ProposedInsight,
    QuranRef,
)
from src.pipeline.insight.guard import scripture_guard
from src.pipeline.leak_guard import LeakDetector, ScriptureLeakError
from src.pipeline.scene_analyzer import analyze_scene
from src.pipeline.schemas import SceneRequest
from src.pipeline.sensitivity import moderate, with_moderation
from src.retrieval.refs import hadith_key, parse_quran, quran_key
from src.scripture.text import sha256_hex

ENGINE_GOLD = (
    Path(__file__).resolve().parents[2] / "tests" / "evaluation" / "scenes" / "engine-gold.json"
)
ABSTAINED = frozenset({EngineStatus.NEEDS_CLARIFICATION, EngineStatus.NO_RELEVANT_EVIDENCE})


class EngineExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scene: str
    expect: Literal["insight", "abstain"]
    hoped: list[str]
    why: str


class EngineGold(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int
    description: str
    scenes: list[EngineExpectation]


def load_engine_gold(path: Path = ENGINE_GOLD) -> EngineGold:
    return EngineGold.model_validate(json.loads(path.read_text(encoding="utf-8")))


class SceneRun(BaseModel):
    scene: str
    expected: str
    status: str
    correct: bool
    insights: int
    relations: list[str]
    evidence: list[str]
    unresolved: list[str]
    leaks: list[str]
    hoped: list[str]
    hoped_found: list[str]
    awaiting_ruling: int
    clarification_question: str | None
    vision_ms: int
    stage_ms: dict[str, int]
    total_ms: int
    cost_usd: float
    calls: int
    # The latency of every model call, by stage, in the order they were made.
    call_ms: dict[str, list[int]] = Field(default_factory=dict)


class EvaluationResult(BaseModel):
    started_at: datetime
    finished_at: datetime
    provider: str
    models: dict[str, str]
    detector_available: int
    runs: list[SceneRun]

    @property
    def cost_usd(self) -> float:
        return sum(run.cost_usd for run in self.runs)


async def resolve_evidence(
    session: AsyncSession, insight: ProposedInsight
) -> tuple[list[str], list[str]]:
    """Return the keys of an insight's evidence and those that name no stored text or fail their hash."""
    keys: list[str] = []
    broken: list[str] = []
    for evidence in (insight.quran, insight.hadith):
        if evidence is None:
            continue
        ref = evidence.ref
        if isinstance(ref, QuranRef):
            key = quran_key(ref.surah, ref.ayah)
            row = (
                await session.execute(
                    select(QuranVerse.text, QuranVerse.text_sha256).where(
                        QuranVerse.surah == ref.surah, QuranVerse.ayah == ref.ayah
                    )
                )
            ).first()
        else:
            key = hadith_key(ref.collection, ref.number)
            row = (
                await session.execute(
                    select(Hadith.text, Hadith.text_sha256).where(
                        Hadith.collection == ref.collection, Hadith.number == ref.number
                    )
                )
            ).first()
        keys.append(key)
        if row is None or sha256_hex(row.text) != row.text_sha256:
            broken.append(key)
    return keys, broken


def insight_texts(insight: ProposedInsight) -> dict[str, str]:
    """Every text of an insight a person reads, keyed by where it is."""
    texts = {"title": insight.title, "glimpse": insight.glimpse, "why.concept": insight.why.concept}
    texts |= {f"explanation.{p.section}": p.text for p in insight.explanation}
    texts |= {f"why.limits.{i}": text for i, text in enumerate(insight.why.limits)}
    texts |= {f"why.clues.{i}": text for i, text in enumerate(insight.why.visible_clues)}
    if insight.why.personalised_because:
        texts["why.personalised_because"] = insight.why.personalised_because
    if insight.small_step is not None:
        texts["small_step"] = insight.small_step.text
    return texts


async def hadith_texts(session: AsyncSession, refs: Sequence[HadithRef]) -> list[str]:
    if not refs:
        return []
    keys = [(ref.collection, ref.number) for ref in refs]
    return list(
        await session.scalars(
            select(Hadith.text).where(tuple_(Hadith.collection, Hadith.number).in_(keys))
        )
    )


def hoped_found(hoped: Sequence[str], evidence: Sequence[str]) -> list[str]:
    """Return the hoped-for keys (ranges allowed) that some evidence key falls in."""
    found = []
    for key in hoped:
        verse_range = parse_quran(key)
        for item in evidence:
            if item.startswith("Q:"):
                surah, ayah = (int(part) for part in item.split(":")[1:])
                if verse_range.contains(surah, ayah):
                    found.append(key)
                    break
    return found


async def check_result(
    session: AsyncSession,
    expectation: EngineExpectation,
    result: EngineResult,
    quran: LeakDetector,
) -> dict[str, object]:
    evidence: list[str] = []
    unresolved: list[str] = []
    leaks: list[str] = []
    refs = [
        i.hadith.ref for i in result.insights if i.hadith and isinstance(i.hadith.ref, HadithRef)
    ]
    guard = scripture_guard(quran, await hadith_texts(session, refs), session)
    for index, insight in enumerate(result.insights):
        keys, broken = await resolve_evidence(session, insight)
        evidence += keys
        unresolved += broken
        refused = await guard.refused(insight_texts(insight))
        leaks += [f"insights.{index}.{field}" for field in refused]
    if result.clarification_question and await guard.leaks([result.clarification_question]):
        leaks.append("clarification_question")
    abstained = result.status in ABSTAINED
    correct = abstained if expectation.expect == "abstain" else result.status is EngineStatus.OK
    return {
        "status": result.status.value,
        "correct": correct,
        "insights": len(result.insights),
        "relations": [insight.relation.value for insight in result.insights],
        "evidence": evidence,
        "unresolved": unresolved,
        "leaks": leaks,
        "hoped_found": hoped_found(expectation.hoped, evidence),
        "awaiting_ruling": len(result.awaiting_ruling),
        "clarification_question": result.clarification_question,
        "stage_ms": {stage.value: ms for stage, ms in result.stage_ms.items()},
    }


EngineFactory = Callable[[CallLog], tuple[ModelClient, InsightEngine]]


def call_latencies(log: CallLog) -> dict[str, list[int]]:
    """Return the latency of each model call by stage, in call order."""
    latencies: dict[str, list[int]] = {}
    for record in log.records:
        latencies.setdefault(record.stage.value, []).append(record.latency_ms)
    return latencies


async def evaluate_scene(
    session: AsyncSession,
    prepared: PreparedScene,
    expectation: EngineExpectation,
    factory: EngineFactory,
    quran: LeakDetector,
    *,
    clock: Callable[[], float] = time.perf_counter,
) -> SceneRun:
    """Run one gold scene through scene analysis and the engine, and check the result."""
    log = CallLog()
    client, engine = factory(log)
    started = clock()
    checked: dict[str, object]
    vision_ms = 0
    # As in the scan workflow, the moderation runs while the scene is described.
    moderation = asyncio.create_task(moderate(prepared.image.model_image, client=client))
    try:
        described = await analyze_scene(
            SceneRequest(image=prepared.image.model_image, detector=prepared.detector),
            client=client,
        )
        scene = with_moderation(described, await moderation)
        vision_ms = round((clock() - started) * 1000)
        result = await engine.propose(
            EngineRequest(scan_id=f"eval-{prepared.gold.id}", scene=scene)
        )
        checked = await check_result(session, expectation, result, quran)
    except (AiCallError, ScriptureLeakError) as error:
        moderation.cancel()
        status = "vision_failed" if isinstance(error, AiCallError) else "vision_leak"
        checked = {"status": status, "correct": False}
    return SceneRun(
        scene=prepared.gold.id,
        expected=expectation.expect,
        hoped=expectation.hoped,
        vision_ms=vision_ms,
        total_ms=round((clock() - started) * 1000),
        cost_usd=round(log.total_cost_usd, 6),
        calls=len(log.records),
        call_ms=call_latencies(log),
        **{
            "insights": 0,
            "relations": [],
            "evidence": [],
            "unresolved": [],
            "leaks": [],
            "hoped_found": [],
            "awaiting_ruling": 0,
            "clarification_question": None,
            "stage_ms": {},
            **checked,
        },
    )


def percentiles(values: Sequence[int]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
    return float(statistics.median(ordered)), float(p95)


class EvaluationSummary(BaseModel):
    """The measures of docs/EVALUATION.md."""

    scenes: int
    correct: int
    leaks: int
    evidence: int
    unresolved: int
    relations: dict[str, int]
    statuses: dict[str, int]
    abstain_expected: int
    abstain_correct: int
    insight_expected: int
    insight_correct: int
    hoped: int
    hoped_found: int
    awaiting_ruling: int
    stages: dict[str, tuple[float, float]]
    cost_per_scan: float
    cost: float


def summary(result: EvaluationResult) -> EvaluationSummary:
    runs = result.runs
    finished = [run for run in runs if run.status not in {"vision_failed", "vision_leak"}]
    stages: dict[str, list[int]] = {}
    for run in finished:
        for stage, ms in run.stage_ms.items():
            stages.setdefault(stage, []).append(ms)
    stages["vision (scene and guard)"] = [run.vision_ms for run in finished]
    stages["whole scan"] = [run.total_ms for run in finished]

    def count(expected: str, *, correct: bool = False) -> int:
        return sum(1 for run in runs if run.expected == expected and (run.correct or not correct))

    return EvaluationSummary(
        scenes=len(runs),
        correct=sum(run.correct for run in runs),
        leaks=sum(len(run.leaks) for run in runs),
        evidence=sum(len(run.evidence) for run in runs),
        unresolved=sum(len(run.unresolved) for run in runs),
        relations=dict(Counter(relation for run in runs for relation in run.relations)),
        statuses=dict(Counter(run.status for run in runs)),
        abstain_expected=count("abstain"),
        abstain_correct=count("abstain", correct=True),
        insight_expected=count("insight"),
        insight_correct=count("insight", correct=True),
        hoped=sum(len(run.hoped) for run in runs),
        hoped_found=sum(len(run.hoped_found) for run in runs),
        awaiting_ruling=sum(run.awaiting_ruling for run in runs),
        stages={name: percentiles(values) for name, values in stages.items()},
        cost_per_scan=result.cost_usd / len(runs) if runs else 0.0,
        cost=result.cost_usd,
    )


async def run_evaluation(
    session: AsyncSession,
    scenes: Sequence[PreparedScene],
    gold: EngineGold,
    factory: EngineFactory,
    quran: LeakDetector,
    *,
    provider: str,
    models: dict[str, str],
    max_cost_usd: float | None = None,
    on_scene: Callable[[SceneRun], Awaitable[None]] | None = None,
) -> EvaluationResult:
    """Evaluate every prepared scene, in order, until the spend cap."""
    started_at = datetime.now(UTC)
    expectations = {item.scene: item for item in gold.scenes}
    runs: list[SceneRun] = []
    for prepared in scenes:
        if max_cost_usd is not None and sum(run.cost_usd for run in runs) >= max_cost_usd:
            break
        run = await evaluate_scene(
            session, prepared, expectations[prepared.gold.id], factory, quran
        )
        runs.append(run)
        if on_scene is not None:
            await on_scene(run)
    return EvaluationResult(
        started_at=started_at,
        finished_at=datetime.now(UTC),
        provider=provider,
        models=models,
        detector_available=sum(1 for scene in scenes if scene.detector.available),
        runs=runs,
    )
