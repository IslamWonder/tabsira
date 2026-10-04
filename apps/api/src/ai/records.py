"""
What each model call cost and how it went.

One `CallRecord` per call, whatever its outcome: provider, model, stage, wall
time, attempts, tokens, cost and error code. Records go to a `CallLog`; the scan
trace, the AI-cost view of the admin area and the benchmark read them there.
The record never holds the prompt, the image or the answer.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from src.ai.errors import AiErrorCode
from src.config import AiProvider, AiStage, ModelPrice

TOKENS_PER_PRICE_UNIT = 1_000_000


class CallKind(StrEnum):
    """The endpoint a call used."""

    CHAT = "chat"
    EMBEDDING = "embedding"
    MODERATION = "moderation"


class Usage(BaseModel):
    """Tokens billed for a call, summed over its attempts."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int = 0
    output_tokens: int = 0
    # Part of output_tokens: the hidden reasoning of a thinking model.
    reasoning_tokens: int = 0
    # Part of input_tokens: served from the provider's prompt cache.
    cached_input_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
        )

    @classmethod
    def from_response(cls, usage: Any) -> Usage:
        """Read the `usage` object of an OpenAI-compatible response; tolerate missing parts."""
        if not isinstance(usage, Mapping):
            return cls()
        output_details = usage.get("completion_tokens_details")
        input_details = usage.get("prompt_tokens_details")
        return cls(
            input_tokens=_count(usage, "prompt_tokens"),
            output_tokens=_count(usage, "completion_tokens"),
            reasoning_tokens=_count(output_details, "reasoning_tokens"),
            cached_input_tokens=_count(input_details, "cached_tokens"),
        )


def _count(container: Any, key: str) -> int:
    """Return a non-negative integer from a mapping, or 0 when it is absent or not a count."""
    if not isinstance(container, Mapping):
        return 0
    value = container.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(value, 0)


def cost_usd(price: ModelPrice | None, usage: Usage) -> float | None:
    """Return what `usage` cost at `price`, or None when the model has no price."""
    if price is None:
        return None
    cached = usage.cached_input_tokens if price.cached_input is not None else 0
    total = (
        (usage.input_tokens - cached) * price.input
        + cached * (price.cached_input or 0.0)
        + usage.output_tokens * price.output
    )
    return total / TOKENS_PER_PRICE_UNIT


class CallRecord(BaseModel):
    """One model call: who served it, how long it took, what it cost, how it ended."""

    model_config = ConfigDict(frozen=True)

    provider: AiProvider
    model: str
    stage: AiStage
    kind: CallKind
    started_at: datetime
    latency_ms: int
    attempts: int
    usage: Usage
    cost_usd: float | None
    ok: bool
    error_code: AiErrorCode | None = None
    # The provider's finish reason of the last attempt (stop, length, ...), when it gave one.
    finish_reason: str | None = None


class CallLog:
    """Collects the records of the calls made through a client."""

    def __init__(self) -> None:
        self.records: list[CallRecord] = []

    def add(self, record: CallRecord) -> None:
        self.records.append(record)

    @property
    def total_cost_usd(self) -> float:
        """Sum of the known costs; calls to a model without a price add nothing."""
        return sum(record.cost_usd or 0.0 for record in self.records)
