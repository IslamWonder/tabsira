from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from src.ai.client import ProviderClient
from src.ai.errors import AiCallError, AiErrorCode
from src.ai.records import CallLog
from src.config import AiProvider, BoxCoordinates
from src.evaluation.benchmark import (
    DEFAULT_CELLS,
    BenchmarkOptions,
    BenchmarkResult,
    Cell,
    CellSummary,
    best,
    percentile,
    provider_factory,
    recommend,
    run_benchmark,
    stat,
)
from tests.benchmark_fixtures import answer, broken, cell, detector_handler, factory, write_gold

MINI = "gpt-5.4-mini-2026-03-17"
NANO = "gpt-5.4-nano-2026-03-17"
OMNI = "omni-moderation-latest"


async def run(tmp_path: Path, make_settings, cells, behaviours, **options) -> BenchmarkResult:
    gold = write_gold(tmp_path)
    settings = make_settings(ai_max_retries=0)
    moments = iter([datetime(2026, 10, 4, 9, tzinfo=UTC), datetime(2026, 10, 4, 9, 30, tzinfo=UTC)])
    async with httpx.AsyncClient(transport=httpx.MockTransport(detector_handler)) as http:
        return await run_benchmark(
            BenchmarkOptions(gold_path=gold, cells=tuple(cells), **options),
            settings=settings,
            http=http,
            factory=factory(behaviours),
            now=lambda: next(moments),
        )


def by_name(result: BenchmarkResult) -> dict[str, CellSummary]:
    return {summary.cell.name: summary for summary in result.cells}


def setting(result: BenchmarkResult, name: str) -> str:
    return next(r.value for r in result.recommendations if r.setting == name)


# ─── Statistics ────────────────────────────────────────────────────


def test_percentiles_use_the_nearest_rank():
    assert percentile([5, 1, 3, 2, 4], 0.5) == 3
    assert percentile([5, 1, 3, 2, 4], 0.95) == 5
    assert percentile([7], 0.95) == 7
    assert stat([]).p50 is None
    assert stat([1000, 3000]).model_dump() == {"count": 2, "p50": 1000, "p95": 3000, "mean": 2000}


def test_a_cell_never_names_a_gpt_oss_model():
    with pytest.raises(ValidationError, match="gpt-oss"):
        Cell(name="x", provider=AiProvider.OVH, model="gpt-oss-120b")


def test_the_default_matrix_covers_both_providers_and_a_smaller_challenger_each():
    names = {c.name for c in DEFAULT_CELLS}

    assert {
        "ovh-qwen3.8-27b",
        "openai-gpt-5.4-mini",
        "ovh-qwen3.5-9b",
        "openai-gpt-5.4-nano",
    } <= names
    assert all(c.guard_model == OMNI for c in DEFAULT_CELLS if c.provider is AiProvider.OPENAI)


# ─── A whole run ───────────────────────────────────────────────────


async def test_the_best_eligible_cell_of_each_provider_becomes_its_default(tmp_path, make_settings):
    cells = [
        cell("ovh-good"),
        cell("ovh-pixels", coordinates=BoxCoordinates.PIXELS),
        cell("openai-good", AiProvider.OPENAI, model=MINI, coordinates="pixels", guard=OMNI),
        cell("openai-nano", AiProvider.OPENAI, model=NANO, coordinates="pixels", guard=OMNI),
    ]
    behaviours = {
        "ovh-good": (answer(box=[0, 0, 500, 500]), 20_000),
        # Thousandths asked for pixels: on a 64-pixel photo the box falls outside.
        "ovh-pixels": (answer(box=[0, 0, 500, 500]), 18_000),
        "openai-good": (answer(box=[0, 0, 32, 32]), 5_000),
        "openai-nano": (answer(box=[0, 0, 32, 32], misses_sensitive=True), 3_000),
    }

    result = await run(tmp_path, make_settings, cells, behaviours, runs=2)

    summaries = by_name(result)
    good = summaries["ovh-good"]
    assert (good.runs, good.ok, good.blind_runs) == (4, 4, 2)
    assert good.schema_valid_rate == 1.0
    assert good.first_try_rate == 1.0
    assert good.entity_recall == 1.0
    assert good.action_recall == 1.0
    assert good.clarification_agreement == 1.0
    assert good.sensitive_accuracy == 1.0
    assert good.detector_iou_median == 1.0
    assert good.blind_box_agreement == 1.0
    assert good.blind_iou_median == 1.0
    assert good.eligible
    assert good.quality == 1.0
    assert good.vision_latency.p95 == 20_000
    assert good.guard_latency.count == 0
    assert good.cost_usd == pytest.approx(6 * 0.002)
    assert good.cost_per_scan_usd == pytest.approx(0.002)

    pixels = summaries["ovh-pixels"]
    assert pixels.box_drop_rate == 1.0
    assert pixels.ineligible_because == ["100% of boxes outside the image"]

    nano = summaries["openai-nano"]
    assert nano.sensitive_false_negatives == 2
    assert nano.ineligible_because == ["missed 2 sensitive scene(s)"]
    assert summaries["openai-good"].guard_latency.count == 4

    assert setting(result, "AI_PROVIDER") == "openai"
    assert setting(result, "AI_OVH__VISION_MODEL") == "Qwen3.8-27B"
    assert setting(result, "AI_OVH__REASONING_EFFORT") == "none"
    assert setting(result, "AI_OVH__BOX_COORDINATES") == "thousandths"
    assert setting(result, "AI_OPENAI__VISION_MODEL") == MINI
    assert setting(result, "AI_OPENAI__GUARD_MODEL") == OMNI
    box_reason = next(
        r.reason for r in result.recommendations if r.setting.endswith("OVH__BOX_COORDINATES")
    )
    assert "thousandths: with the detector hidden, 0% of boxes outside the image" in box_reason
    assert "pixels: with the detector hidden, 100% of boxes outside the image" in box_reason
    provider_reason = result.recommendations[0].reason
    assert provider_reason.startswith("openai-good: quality 1.00")
    assert "against ovh-good" in provider_reason

    assert result.scenes == ["phone", "wine"]
    assert result.detector_model == "yoloe-test"
    assert result.detector_available == 2
    assert result.prompt_version is not None
    assert result.validation_latency.count == 2
    assert result.total_cost_usd == pytest.approx(sum(s.cost_usd for s in result.cells))
    assert (result.finished_at - result.started_at).seconds == 1800
    assert sum(1 for r in result.results if r.blind) == 8


async def test_failures_leaks_and_partial_validity_are_counted(tmp_path, make_settings):
    leaky = "هاتف" + chr(0x06D6)
    calls = {"n": 0}

    def half_broken(call):
        calls["n"] += 1
        return broken(call) if calls["n"] % 2 else answer(box=None)(call)

    cells = [cell("down"), cell("leaky"), cell("flaky"), cell("offline")]
    behaviours = {
        "down": (broken, 1000),
        "offline": (lambda _: AiCallError(AiErrorCode.NETWORK, "no route"), 33_000),
        "leaky": (answer(description=leaky), 1000),
        "flaky": (half_broken, 1000),
    }

    result = await run(tmp_path, make_settings, cells, behaviours, runs=1, blind_runs=0)

    summaries = by_name(result)
    down = summaries["down"]
    assert (down.failed, down.ok) == (2, 0)
    assert down.errors == {"timeout": 2}
    assert down.schema_valid_rate == 0.0
    assert down.ineligible_because == ["no valid answer"]
    leak = summaries["leaky"]
    assert leak.leaks == 2
    assert leak.errors == {"scripture_leak": 2}
    assert leak.schema_valid_rate == 1.0
    assert leak.ineligible_because == ["no valid answer"]
    flaky = summaries["flaky"]
    assert flaky.schema_valid_rate == 0.5
    assert flaky.ineligible_because[0] == "valid answers 50% < 90%"
    assert flaky.boxes_given == 0
    assert flaky.box_drop_rate is None
    offline = summaries["offline"]
    assert (offline.unreachable, offline.failed) == (2, 2)
    assert offline.errors == {"network": 2}
    assert offline.schema_valid_rate is None
    assert offline.vision_latency.count == 0
    assert offline.ineligible_because == ["no valid answer"]
    assert down.unreachable == 0
    assert setting(result, "AI_OVH__VISION_MODEL") == "(leave empty)"
    assert "down: no valid answer" in result.recommendations[0].reason
    assert not any(r.setting == "AI_PROVIDER" for r in result.recommendations)


async def test_boxes_far_from_the_detectors_are_not_eligible(tmp_path, make_settings):
    cells = [cell("drifting")]
    behaviours = {"drifting": (answer(box=[600, 600, 1000, 1000], description="طفل يقف"), 1000)}

    result = await run(tmp_path, make_settings, cells, behaviours, runs=1)

    summary = by_name(result)["drifting"]
    assert summary.detector_iou_median == 0.0
    assert summary.blind_box_agreement == 0.0
    assert summary.ineligible_because == ["median IoU with the detector 0.00"]
    assert summary.findings == {"identity word: «طفل»": 2}
    assert summary.wrong_language == 0
    assert summary.identity_inferences == 2


async def test_no_run_starts_once_the_budget_is_spent(tmp_path, make_settings):
    cells = [cell("spender")]
    behaviours = {"spender": (answer(box=None), 1000)}

    result = await run(
        tmp_path, make_settings, cells, behaviours, runs=2, concurrency=1, max_cost_usd=0.001
    )

    summary = by_name(result)["spender"]
    assert summary.ok == 1
    assert summary.skipped == 3
    assert summary.runs == 4
    assert [r.status for r in result.results if r.blind] == ["skipped", "skipped"]


async def test_a_scene_filter_runs_only_the_named_scenes(tmp_path, make_settings):
    result = await run(
        tmp_path,
        make_settings,
        [cell("one")],
        {"one": (answer(box=None), 1000)},
        runs=1,
        blind_runs=0,
        scene_ids=("wine",),
    )

    assert result.scenes == ["wine"]
    assert result.blind_runs_per_scene == 0


# ─── Choosing ──────────────────────────────────────────────────────


def summary_of(
    name: str, provider: AiProvider, quality: float, p95: int, cost: float
) -> CellSummary:
    return CellSummary.model_construct(
        cell=Cell(name=name, provider=provider, model=name),
        quality=quality,
        eligible=True,
        entity_recall=1.0,
        violations_per_run=0.0,
        vision_latency=stat([p95]),
        cost_per_scan_usd=cost,
        blind_box_drop_rate=None,
        blind_box_agreement=None,
    )


def test_close_qualities_are_decided_by_latency_then_cost():
    slow = summary_of("slow", AiProvider.OVH, 0.95, 9000, 0.001)
    fast = summary_of("fast", AiProvider.OVH, 0.92, 4000, 0.004)
    cheap = summary_of("cheap", AiProvider.OVH, 0.91, 4000, 0.001)
    weak = summary_of("weak", AiProvider.OVH, 0.5, 1000, 0.0001)

    assert best([slow, fast, cheap, weak]) is cheap
    assert best([]) is None


def test_one_provider_alone_is_chosen_against_nobody():
    only = summary_of("only", AiProvider.OVH, 0.9, 4000, 0.001)

    recommendations = recommend([only])

    assert recommendations[0].setting == "AI_PROVIDER"
    assert recommendations[0].reason.endswith("(against no other provider eligible)")
    assert not any(r.setting.startswith("AI_OPENAI__") for r in recommendations)
    assert not any(r.setting.endswith("GUARD_MODEL") for r in recommendations)


def test_the_real_provider_factory_builds_clients_with_the_cells_settings(make_settings):
    settings = make_settings(ai_timeout_seconds=7, ai_openai={"api_key": "k"})
    log = CallLog()
    http = httpx.AsyncClient()
    openai = DEFAULT_CELLS[-1]

    client = provider_factory(settings, http)(openai, log)

    assert isinstance(client, ProviderClient)
    assert client.provider is AiProvider.OPENAI
    assert client.settings.vision_model == openai.model
    assert client.settings.guard_model == OMNI
    assert client.settings.reasoning_effort == "none"
    assert client.settings.api_key.get_secret_value() == "k"
    ovh = provider_factory(settings, http)(DEFAULT_CELLS[0], log)
    assert ovh.settings.box_coordinates is BoxCoordinates.THOUSANDTHS
