"""
The vision benchmark: the same gold scenes through each candidate model.

Each scene is validated once and sent to the detector once; then, for every
cell (provider, model, reasoning effort, box coordinates) and every run, the
scene analyzer describes it and the sensitivity guard judges it, and the
answer is scored against the gold scene. Blind runs hide the detector from the
model: given the detector's boxes, models copy them, so only a blind run shows
where a model's own boxes land and whether it follows the coordinate system. Numbers are aggregated per cell and
per stage, and a fixed rule turns them into recommended defaults, so the same
measurements always give the same recommendation.
"""

from __future__ import annotations

import asyncio
import math
import statistics
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.ai.client import ModelClient, ProviderClient
from src.ai.errors import AiCallError
from src.ai.records import CallLog, CallRecord
from src.config import (
    AiProvider,
    AiStage,
    BoxCoordinates,
    Settings,
    refuse_forbidden_model,
)
from src.evaluation.gold import GoldScene, GoldSet, load_gold
from src.evaluation.scoring import SceneScore, score_scene
from src.pipeline.detector import DetectorClient
from src.pipeline.image_validator import validate_image
from src.pipeline.leak_guard import ScriptureLeakError
from src.pipeline.scene_analyzer import analyze_scene
from src.pipeline.schemas import (
    DetectorRequest,
    DetectorResult,
    ImageUpload,
    SceneAnalysis,
    SceneRequest,
    SensitivityRequest,
    ValidatedImage,
)
from src.pipeline.sensitivity import check_sensitivity

OPENAI_MODERATION = "omni-moderation-latest"
# Eligibility for a default: the answer must validate, no sensitive scene may be
# missed, and boxes must land where the detector puts them.
MIN_VALID_RATE = 0.9
MAX_BOX_DROP_RATE = 0.2
MIN_DETECTOR_IOU = 0.5
# A blind box agrees with the detector when it overlaps one of its boxes this much.
AGREEMENT_IOU = 0.5
# Cells whose quality is within this margin of the best are equals; the faster wins.
QUALITY_MARGIN = 0.05


class Cell(BaseModel):
    """One candidate: a provider's model with its call settings."""

    model_config = ConfigDict(frozen=True)

    name: str
    provider: AiProvider
    model: str
    # Empty leaves the provider's default (Qwen on OVH then thinks before answering).
    reasoning_effort: str = ""
    box_coordinates: BoxCoordinates = BoxCoordinates.PIXELS
    guard_model: str = ""
    role: str = "primary"

    @field_validator("model", "guard_model")
    @classmethod
    def _no_gpt_oss(cls, value: str) -> str:
        return refuse_forbidden_model(value)


# The matrix of docs/research/ai-providers.md §6 for the vision stage, plus the
# two switches that matter on OVH: thinking on or off, and the box grid.
DEFAULT_CELLS = (
    Cell(
        name="ovh-qwen3.8-27b-thinking",
        provider=AiProvider.OVH,
        model="Qwen3.8-27B",
        box_coordinates=BoxCoordinates.THOUSANDTHS,
        role="primary, thinking on (provider default)",
    ),
    Cell(
        name="ovh-qwen3.8-27b",
        provider=AiProvider.OVH,
        model="Qwen3.8-27B",
        reasoning_effort="none",
        box_coordinates=BoxCoordinates.THOUSANDTHS,
        role="primary, thinking off",
    ),
    Cell(
        name="ovh-qwen3.8-27b-pixels",
        provider=AiProvider.OVH,
        model="Qwen3.8-27B",
        reasoning_effort="none",
        box_coordinates=BoxCoordinates.PIXELS,
        role="variant: boxes asked in pixels",
    ),
    Cell(
        name="ovh-qwen3.5-9b",
        provider=AiProvider.OVH,
        model="Qwen3.5-9B",
        reasoning_effort="none",
        box_coordinates=BoxCoordinates.THOUSANDTHS,
        role="smaller challenger",
    ),
    Cell(
        name="openai-gpt-5.4-mini",
        provider=AiProvider.OPENAI,
        model="gpt-5.4-mini-2026-03-17",
        reasoning_effort="none",
        guard_model=OPENAI_MODERATION,
        role="primary, no reasoning",
    ),
    Cell(
        name="openai-gpt-5.4-mini-low",
        provider=AiProvider.OPENAI,
        model="gpt-5.4-mini-2026-03-17",
        reasoning_effort="low",
        guard_model=OPENAI_MODERATION,
        role="variant: low reasoning",
    ),
    Cell(
        name="openai-gpt-5.4-nano",
        provider=AiProvider.OPENAI,
        model="gpt-5.4-nano-2026-03-17",
        reasoning_effort="none",
        guard_model=OPENAI_MODERATION,
        role="smaller challenger",
    ),
)


class BenchmarkOptions(BaseModel):
    gold_path: Path
    cells: tuple[Cell, ...] = DEFAULT_CELLS
    runs: int = Field(default=2, ge=1)
    # Extra runs per scene and cell with the detector hidden, to measure the boxes.
    blind_runs: int = Field(default=1, ge=0)
    scene_ids: tuple[str, ...] = ()
    # Calls in flight per provider at a time.
    concurrency: int = Field(default=4, ge=1)
    # No new run starts once this much has been spent.
    max_cost_usd: float = Field(default=5.0, gt=0)


class Stat(BaseModel):
    """Milliseconds over a set of samples."""

    count: int
    p50: int | None
    p95: int | None
    mean: int | None


def percentile(values: Sequence[float], share: float) -> float:
    """Nearest-rank percentile of a non-empty sample."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


def stat(values: Sequence[float]) -> Stat:
    if not values:
        return Stat(count=0, p50=None, p95=None, mean=None)
    return Stat(
        count=len(values),
        p50=round(percentile(values, 0.5)),
        p95=round(percentile(values, 0.95)),
        mean=round(statistics.fmean(values)),
    )


RunStatus = Literal["ok", "failed", "leak", "skipped"]


class RunResult(BaseModel):
    """One scene through one cell, once."""

    cell: str
    scene: str
    run: int
    blind: bool = False
    status: RunStatus
    error: str | None = None
    vision: CallRecord | None = None
    guard: CallRecord | None = None
    score: SceneScore | None = None
    analysis: SceneAnalysis | None = None

    @property
    def cost_usd(self) -> float:
        return sum(record.cost_usd or 0.0 for record in (self.vision, self.guard) if record)


class PreparedScene(BaseModel):
    """A gold scene after validation and detection, shared by every cell."""

    model_config = ConfigDict(frozen=True)

    gold: GoldScene
    image: ValidatedImage
    validation_ms: int
    detector: DetectorResult


class CellSummary(BaseModel):
    """Everything measured for one cell."""

    cell: Cell
    runs: int
    ok: int
    failed: int
    leaks: int
    skipped: int
    errors: dict[str, int]
    schema_valid_rate: float | None
    first_try_rate: float | None
    entity_recall: float | None
    action_recall: float | None
    forbidden_claims: int
    identity_inferences: int
    hallucinated_entities: int
    violations_per_run: float | None
    sensitive_accuracy: float | None
    sensitive_false_negatives: int
    sensitive_false_positives: int
    clarification_agreement: float | None
    boxes_given: int
    boxes_dropped: int
    box_drop_rate: float | None
    detector_iou_median: float | None
    blind_runs: int
    blind_boxes_given: int
    blind_box_drop_rate: float | None
    # Share of the model's own boxes that overlap a detector box (IoU >= AGREEMENT_IOU).
    blind_box_agreement: float | None
    blind_iou_median: float | None
    vision_latency: Stat
    guard_latency: Stat
    input_tokens_mean: float | None
    output_tokens_mean: float | None
    reasoning_tokens_mean: float | None
    cost_usd: float
    cost_per_scan_usd: float | None
    quality: float | None
    eligible: bool
    ineligible_because: list[str]
    findings: dict[str, int]


class Recommendation(BaseModel):
    setting: str
    value: str
    reason: str


class BenchmarkResult(BaseModel):
    started_at: datetime
    finished_at: datetime
    gold_version: int
    runs_per_scene: int
    blind_runs_per_scene: int
    scenes: list[str]
    prompt_version: str | None
    detector_model: str | None
    detector_available: int
    validation_latency: Stat
    detector_latency: Stat
    cells: list[CellSummary]
    recommendations: list[Recommendation]
    total_cost_usd: float
    results: list[RunResult]


ClientFactory = Callable[[Cell, CallLog], ModelClient]
HIDDEN_DETECTOR = DetectorResult(available=False, latency_ms=0, error="hidden")


def provider_factory(settings: Settings, http: httpx.AsyncClient) -> ClientFactory:
    """Build real provider clients for the cells, from the configured keys and limits."""

    def build(cell: Cell, log: CallLog) -> ModelClient:
        base = settings.ai_ovh if cell.provider == AiProvider.OVH else settings.ai_openai
        block = base.model_copy(
            update={
                "vision_model": cell.model,
                "guard_model": cell.guard_model,
                "reasoning_effort": cell.reasoning_effort,
                "box_coordinates": cell.box_coordinates,
            }
        )
        return ProviderClient(
            cell.provider,
            block,
            http,
            timeout_seconds=settings.ai_timeout_seconds,
            max_retries=settings.ai_max_retries,
            backoff_seconds=settings.ai_retry_backoff_seconds,
            log=log,
        )

    return build


async def prepare_scenes(
    gold: GoldSet,
    directory: Path,
    scene_ids: Sequence[str],
    *,
    settings: Settings,
    detector: DetectorClient,
    clock: Callable[[], float] = time.perf_counter,
) -> list[PreparedScene]:
    """Validate each image and run the detector on it, once."""
    prepared = []
    for gold_scene in gold.scenes:
        if scene_ids and gold_scene.id not in scene_ids:
            continue
        data = (directory / gold_scene.image).read_bytes()
        started = clock()
        image = validate_image(
            ImageUpload(data=data),
            max_bytes=settings.image_max_bytes,
            max_pixels=settings.image_max_pixels,
        )
        validation_ms = round((clock() - started) * 1000)
        detected = await detector.detect(DetectorRequest(image=image.model_image))
        prepared.append(
            PreparedScene(
                gold=gold_scene, image=image, validation_ms=validation_ms, detector=detected
            )
        )
    return prepared


class _Budget:
    """What has been spent so far; a run checks it before it starts."""

    def __init__(self, limit: float) -> None:
        self.limit = limit
        self.spent = 0.0

    @property
    def exhausted(self) -> bool:
        return self.spent >= self.limit


async def _run_one(
    cell: Cell,
    scene: PreparedScene,
    run: int,
    *,
    gold: GoldSet,
    factory: ClientFactory,
    gate: asyncio.Semaphore,
    budget: _Budget,
    blind: bool = False,
) -> RunResult:
    async with gate:
        if budget.exhausted:
            return RunResult(
                cell=cell.name, scene=scene.gold.id, run=run, blind=blind, status="skipped"
            )
        log = CallLog()
        client = factory(cell, log)
        detector = HIDDEN_DETECTOR if blind else scene.detector
        request = SceneRequest(image=scene.image.model_image, detector=detector)
        status: RunStatus = "ok"
        error = None
        analysis = None
        score = None
        try:
            described = await analyze_scene(request, client=client)
            analysis = await check_sensitivity(
                SensitivityRequest(image=scene.image.model_image, scene=described), client=client
            )
            reference = scene.detector.detections if blind else ()
            score = score_scene(analysis, scene.gold, gold.rules, reference)
        except AiCallError as failure:
            status, error = "failed", failure.code.value
        except ScriptureLeakError as leak:
            status, error = "leak", str(leak)
        vision = next((r for r in log.records if r.stage is AiStage.VISION), None)
        guard = next((r for r in log.records if r.stage is AiStage.GUARD), None)
        result = RunResult(
            cell=cell.name,
            scene=scene.gold.id,
            run=run,
            blind=blind,
            status=status,
            error=error,
            vision=vision,
            guard=guard,
            score=score,
            analysis=analysis,
        )
        budget.spent += result.cost_usd
        return result


async def run_cells(
    scenes: Sequence[PreparedScene],
    gold: GoldSet,
    options: BenchmarkOptions,
    factory: ClientFactory,
) -> list[RunResult]:
    """Run every cell on every scene, `options.runs` times, within the budget."""
    gates = {provider: asyncio.Semaphore(options.concurrency) for provider in AiProvider}
    budget = _Budget(options.max_cost_usd)
    jobs = [
        _run_one(
            cell,
            scene,
            run,
            gold=gold,
            factory=factory,
            gate=gates[cell.provider],
            budget=budget,
        )
        for run in range(1, options.runs + 1)
        for scene in scenes
        for cell in options.cells
    ]
    jobs += [
        _run_one(
            cell,
            scene,
            run,
            gold=gold,
            factory=factory,
            gate=gates[cell.provider],
            budget=budget,
            blind=True,
        )
        for run in range(1, options.blind_runs + 1)
        for scene in scenes
        for cell in options.cells
    ]
    return list(await asyncio.gather(*jobs))


def _mean(values: Sequence[float]) -> float | None:
    return round(statistics.fmean(values), 4) if values else None


def _rate(hits: int, total: int) -> float | None:
    return round(hits / total, 4) if total else None


def summarize(cell: Cell, results: Sequence[RunResult]) -> CellSummary:
    """Aggregate one cell's runs."""
    everything = [result for result in results if result.cell == cell.name]
    mine = [result for result in everything if not result.blind]
    attempted = [result for result in mine if result.status != "skipped"]
    blind = [r.score for r in everything if r.blind and r.score is not None]
    blind_given = sum(score.boxes_given for score in blind)
    blind_ious = [value for score in blind for value in score.reference_ious]
    answered = [result for result in attempted if result.status in {"ok", "leak"}]
    scores = [result.score for result in attempted if result.score is not None]
    visions = [result.vision for result in attempted if result.vision is not None]
    guards = [result.guard for result in attempted if result.guard is not None]
    first_try = [
        result for result in answered if result.vision is not None and result.vision.attempts == 1
    ]
    errors: dict[str, int] = {}
    for result in attempted:
        if result.error is not None:
            key = result.error if result.status == "failed" else "scripture_leak"
            errors[key] = errors.get(key, 0) + 1

    with_actions = [score for score in scores if score.expected_actions_total]
    clarified = [score for score in scores if score.clarification_expected is not None]
    ious = [value for score in scores for value in score.detector_ious]
    given = sum(score.boxes_given for score in scores)
    dropped = sum(score.boxes_dropped for score in scores)
    violations = sum(score.violations for score in scores)
    scans = [result.cost_usd for result in attempted if result.vision is not None]

    summary = CellSummary(
        cell=cell,
        runs=len(mine),
        ok=sum(1 for result in mine if result.status == "ok"),
        failed=sum(1 for result in mine if result.status == "failed"),
        leaks=sum(1 for result in mine if result.status == "leak"),
        skipped=len(mine) - len(attempted),
        errors=errors,
        schema_valid_rate=_rate(len(answered), len(attempted)),
        first_try_rate=_rate(len(first_try), len(attempted)),
        entity_recall=_mean([s.required_found / s.required_total for s in scores]),
        action_recall=_mean(
            [s.expected_actions_found / s.expected_actions_total for s in with_actions]
        ),
        forbidden_claims=sum(len(score.forbidden_claims) for score in scores),
        identity_inferences=sum(len(score.identity_inferences) for score in scores),
        hallucinated_entities=sum(len(score.hallucinated_entities) for score in scores),
        violations_per_run=_rate(violations, len(scores)),
        sensitive_accuracy=_rate(sum(1 for s in scores if s.sensitive_correct), len(scores)),
        sensitive_false_negatives=sum(
            1 for s in scores if s.sensitive_expected and not s.sensitive_predicted
        ),
        sensitive_false_positives=sum(
            1 for s in scores if s.sensitive_predicted and not s.sensitive_expected
        ),
        clarification_agreement=_rate(
            sum(1 for s in clarified if s.clarification_asked == s.clarification_expected),
            len(clarified),
        ),
        boxes_given=given,
        boxes_dropped=dropped,
        box_drop_rate=_rate(dropped, given),
        detector_iou_median=round(statistics.median(ious), 4) if ious else None,
        blind_runs=sum(1 for r in everything if r.blind and r.status != "skipped"),
        blind_boxes_given=blind_given,
        blind_box_drop_rate=_rate(sum(score.boxes_dropped for score in blind), blind_given),
        blind_box_agreement=_rate(
            sum(1 for value in blind_ious if value >= AGREEMENT_IOU), len(blind_ious)
        ),
        blind_iou_median=round(statistics.median(blind_ious), 4) if blind_ious else None,
        vision_latency=stat([record.latency_ms for record in visions]),
        guard_latency=stat([record.latency_ms for record in guards]),
        input_tokens_mean=_mean([record.usage.input_tokens for record in visions]),
        output_tokens_mean=_mean([record.usage.output_tokens for record in visions]),
        reasoning_tokens_mean=_mean([record.usage.reasoning_tokens for record in visions]),
        cost_usd=round(sum(result.cost_usd for result in everything), 6),
        cost_per_scan_usd=round(statistics.fmean(scans), 6) if scans else None,
        quality=None,
        eligible=False,
        ineligible_because=[],
        findings=_findings(scores),
    )
    return _judged(summary)


def _findings(scores: Sequence[SceneScore]) -> dict[str, int]:
    """Each violation and each missing entity, with how often it happened."""
    counts: dict[str, int] = {}
    for score in scores:
        found = (
            score.forbidden_claims
            + [f"identity word: «{word}»" for word in score.identity_inferences]
            + [f"invented: «{word}»" for word in score.hallucinated_entities]
            + [f"missing: «{word}»" for word in score.missing_entities]
        )
        for finding in found:
            counts[finding] = counts.get(finding, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _judged(summary: CellSummary) -> CellSummary:
    """Add the quality score and the eligibility verdict to a summary."""
    reasons = []
    if summary.schema_valid_rate is None or summary.entity_recall is None:
        return summary.model_copy(update={"ineligible_because": ["no valid answer"]})
    if summary.schema_valid_rate < MIN_VALID_RATE:
        reasons.append(f"valid answers {summary.schema_valid_rate:.0%} < {MIN_VALID_RATE:.0%}")
    if summary.sensitive_false_negatives:
        reasons.append(f"missed {summary.sensitive_false_negatives} sensitive scene(s)")
    drop = max(summary.box_drop_rate or 0.0, summary.blind_box_drop_rate or 0.0)
    if drop > MAX_BOX_DROP_RATE:
        reasons.append(f"{drop:.0%} of boxes outside the image")
    if summary.detector_iou_median is not None and summary.detector_iou_median < MIN_DETECTOR_IOU:
        reasons.append(f"median IoU with the detector {summary.detector_iou_median:.2f}")
    quality = (
        summary.schema_valid_rate
        * (summary.sensitive_accuracy or 0.0)
        * summary.entity_recall
        / (1 + (summary.violations_per_run or 0.0))
    )
    return summary.model_copy(
        update={
            "quality": round(quality, 4),
            "eligible": not reasons,
            "ineligible_because": reasons,
        }
    )


def best(summaries: Sequence[CellSummary]) -> CellSummary | None:
    """Return the eligible cell to choose: best quality, then lowest p95, then cost."""
    eligible = [summary for summary in summaries if summary.eligible]
    if not eligible:
        return None
    top = max(summary.quality or 0.0 for summary in eligible)
    close = [s for s in eligible if (s.quality or 0.0) >= top - QUALITY_MARGIN]
    return min(
        close,
        key=lambda s: (s.vision_latency.p95 or math.inf, s.cost_per_scan_usd or math.inf),
    )


def _describe(summary: CellSummary) -> str:
    return (
        f"{summary.cell.name}: quality {summary.quality:.2f}, entity recall "
        f"{summary.entity_recall or 0:.0%}, {summary.violations_per_run or 0:.2f} violations "
        f"per run, vision p95 {summary.vision_latency.p95} ms, "
        f"${summary.cost_per_scan_usd or 0:.4f} per scan"
    )


def recommend(summaries: Sequence[CellSummary]) -> list[Recommendation]:
    """Turn the measurements into default settings, with the numbers behind each."""
    recommendations: list[Recommendation] = []
    winners: list[CellSummary] = []
    for provider in AiProvider:
        mine = [summary for summary in summaries if summary.cell.provider is provider]
        if not mine:
            continue
        prefix = f"AI_{provider.value.upper()}__"
        chosen = best(mine)
        if chosen is None:
            reasons = "; ".join(f"{s.cell.name}: {', '.join(s.ineligible_because)}" for s in mine)
            recommendations.append(
                Recommendation(
                    setting=f"{prefix}VISION_MODEL",
                    value="(leave empty)",
                    reason=f"no eligible cell ({reasons})",
                )
            )
            continue
        winners.append(chosen)
        why = _describe(chosen)
        recommendations += [
            Recommendation(setting=f"{prefix}VISION_MODEL", value=chosen.cell.model, reason=why),
            Recommendation(
                setting=f"{prefix}REASONING_EFFORT",
                value=chosen.cell.reasoning_effort or "(empty)",
                reason=f"the setting of {chosen.cell.name}",
            ),
            Recommendation(
                setting=f"{prefix}BOX_COORDINATES",
                value=chosen.cell.box_coordinates.value,
                reason=_box_reason(chosen, mine),
            ),
        ]
        if chosen.cell.guard_model:
            recommendations.append(
                Recommendation(
                    setting=f"{prefix}GUARD_MODEL",
                    value=chosen.cell.guard_model,
                    reason=(
                        f"image moderation p95 {chosen.guard_latency.p95} ms over "
                        f"{chosen.guard_latency.count} calls, "
                        f"{chosen.sensitive_false_positives} false positive(s)"
                    ),
                )
            )
    overall = best(winners)
    if overall is not None:
        others = [w for w in winners if w is not overall]
        against = "; ".join(_describe(other) for other in others) or "no other provider eligible"
        recommendations.insert(
            0,
            Recommendation(
                setting="AI_PROVIDER",
                value=overall.cell.provider.value,
                reason=f"{_describe(overall)} (against {against})",
            ),
        )
    return recommendations


def _box_reason(chosen: CellSummary, mine: Sequence[CellSummary]) -> str:
    def boxes(summary: CellSummary) -> str:
        drop = summary.blind_box_drop_rate
        agree = summary.blind_box_agreement
        return (
            f"{summary.cell.box_coordinates.value}: with the detector hidden, "
            f"{'n/a' if drop is None else f'{drop:.0%}'} of boxes outside the image and "
            f"{'n/a' if agree is None else f'{agree:.0%}'} on a detector box"
        )

    variants = [
        summary
        for summary in mine
        if summary.cell.model == chosen.cell.model
        and summary.cell.reasoning_effort == chosen.cell.reasoning_effort
        and summary.cell.box_coordinates is not chosen.cell.box_coordinates
    ]
    return "; ".join(boxes(summary) for summary in [chosen, *variants])


async def run_benchmark(
    options: BenchmarkOptions,
    *,
    settings: Settings,
    http: httpx.AsyncClient,
    factory: ClientFactory | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> BenchmarkResult:
    """Prepare the scenes, run every cell, aggregate and recommend."""
    started_at = now()
    gold = load_gold(options.gold_path)
    detector = DetectorClient(
        settings.detector_url, http, timeout_seconds=settings.detector_timeout_seconds
    )
    scenes = await prepare_scenes(
        gold, options.gold_path.parent, options.scene_ids, settings=settings, detector=detector
    )
    results = await run_cells(scenes, gold, options, factory or provider_factory(settings, http))
    summaries = [summarize(cell, results) for cell in options.cells]
    detected = [scene.detector for scene in scenes if scene.detector.available]
    analyses = [result.analysis for result in results if result.analysis is not None]
    return BenchmarkResult(
        started_at=started_at,
        finished_at=now(),
        gold_version=gold.version,
        runs_per_scene=options.runs,
        blind_runs_per_scene=options.blind_runs,
        scenes=[scene.gold.id for scene in scenes],
        prompt_version=analyses[0].prompt_version if analyses else None,
        detector_model=detected[0].model if detected else None,
        detector_available=len(detected),
        validation_latency=stat([scene.validation_ms for scene in scenes]),
        detector_latency=stat([scene.detector.latency_ms for scene in scenes]),
        cells=summaries,
        recommendations=recommend(summaries),
        total_cost_usd=round(sum(result.cost_usd for result in results), 6),
        results=results,
    )
