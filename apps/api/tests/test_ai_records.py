from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.ai.records import CallKind, CallLog, CallRecord, Usage, cost_usd
from src.config import AiProvider, AiStage, ModelPrice


def test_usage_is_read_from_an_openai_compatible_usage_object():
    usage = Usage.from_response(
        {
            "prompt_tokens": 1342,
            "completion_tokens": 173,
            "prompt_tokens_details": {"cached_tokens": 1024},
            "completion_tokens_details": {"reasoning_tokens": 114},
        }
    )

    assert usage == Usage(
        input_tokens=1342, output_tokens=173, reasoning_tokens=114, cached_input_tokens=1024
    )


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "not a mapping",
        {},
        {"prompt_tokens": "12", "completion_tokens": True, "completion_tokens_details": None},
        {"prompt_tokens": -3, "completion_tokens_details": {"reasoning_tokens": 2.5}},
    ],
)
def test_usage_tolerates_missing_or_malformed_counts(raw):
    assert Usage.from_response(raw) == Usage()


def test_usage_adds_up_over_attempts():
    first = Usage(input_tokens=10, output_tokens=5, reasoning_tokens=3, cached_input_tokens=1)
    second = Usage(input_tokens=1, output_tokens=2, reasoning_tokens=1, cached_input_tokens=0)

    assert first + second == Usage(
        input_tokens=11, output_tokens=7, reasoning_tokens=4, cached_input_tokens=1
    )


def test_cost_uses_the_price_per_million_tokens():
    price = ModelPrice(input=0.47, output=3.19)
    usage = Usage(input_tokens=1_000_000, output_tokens=500_000, cached_input_tokens=400_000)

    # Without a cache price, cached tokens are billed as ordinary input.
    assert cost_usd(price, usage) == pytest.approx(0.47 + 1.595)


def test_cached_input_is_billed_at_its_own_price():
    price = ModelPrice(input=0.75, output=4.5, cached_input=0.075)
    usage = Usage(input_tokens=2000, output_tokens=100, cached_input_tokens=1000)

    assert cost_usd(price, usage) == pytest.approx((1000 * 0.75 + 1000 * 0.075 + 100 * 4.5) / 1e6)


def test_a_model_without_a_price_has_no_cost():
    assert cost_usd(None, Usage(input_tokens=5)) is None


def record(cost: float | None) -> CallRecord:
    return CallRecord(
        provider=AiProvider.OVH,
        model="m",
        stage=AiStage.VISION,
        kind=CallKind.CHAT,
        started_at=datetime(2026, 10, 4, tzinfo=UTC),
        latency_ms=12,
        attempts=1,
        usage=Usage(),
        cost_usd=cost,
        ok=True,
    )


def test_the_call_log_sums_known_costs():
    log = CallLog()
    log.add(record(0.25))
    log.add(record(None))
    log.add(record(0.5))

    assert len(log.records) == 3
    assert log.total_cost_usd == pytest.approx(0.75)
