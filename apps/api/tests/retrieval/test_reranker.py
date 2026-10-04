from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from src.ai.client import ProviderClient
from src.ai.errors import AiCallError, AiErrorCode
from src.config import AiProvider, AiStage, OpenAISettings
from src.retrieval.reranker import (
    MAX_PASSAGE_CHARS,
    MAX_PASSAGES,
    LlmRanking,
    LlmReranker,
    RerankerClient,
    RerankOutcome,
    llm_rerank,
)
from tests.fakes import FakeModelClient
from tests.scripture.fixtures import verse_text


def client_with(handler: Callable[[httpx.Request], httpx.Response]) -> RerankerClient:
    ticks = iter(range(0, 1000, 5))
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return RerankerClient(
        "http://vision.local/", http, timeout_seconds=2.0, clock=lambda: next(ticks) / 1000
    )


async def test_scores_come_back_in_passage_order_and_long_input_is_cut():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        assert request.url == "http://vision.local/rerank"
        scores = [0.5] * len(body["passages"])
        return httpx.Response(200, json={"scores": scores, "model": "bge", "ms": 30})

    outcome = await client_with(handler).rerank("q", ["x" * (MAX_PASSAGE_CHARS + 9)] * 70)

    assert outcome.scores == [0.5] * MAX_PASSAGES
    assert (outcome.model, outcome.error, outcome.latency_ms) == ("bge", None, 5)
    assert len(seen[0]["passages"][0]) == MAX_PASSAGE_CHARS


async def test_nothing_to_rerank_makes_no_call():
    outcome = await client_with(lambda _request: pytest.fail("called")).rerank("q", [])

    assert outcome.scores == []


@pytest.mark.parametrize(
    ("handler", "reason"),
    [
        (lambda _r: (_ for _ in ()).throw(httpx.ReadTimeout("slow")), "timeout"),
        (lambda _r: (_ for _ in ()).throw(httpx.ConnectError("down")), "unreachable"),
        (lambda _r: httpx.Response(503, json={"error": "reranker_unavailable"}), "http_503"),
        (lambda _r: httpx.Response(200, text="not json"), "invalid_response"),
        (
            lambda _r: httpx.Response(200, json={"scores": [0.1], "model": "m", "ms": 1}),
            "invalid_response",
        ),
    ],
)
async def test_a_reranker_that_fails_is_skipped_with_its_reason(handler, reason):
    outcome = await client_with(handler).rerank("q", ["a", "b"])

    assert outcome.scores is None
    assert outcome.error == reason


async def test_the_llm_baseline_scores_every_numbered_passage():
    answer = LlmRanking.model_validate(
        {
            "passages": [
                {"number": 2, "relevance": 9},
                {"number": 1, "relevance": 3},
                {"number": 7, "relevance": 10},
            ]
        }
    )
    model = FakeModelClient(answers=[answer])

    scores = await llm_rerank(model, "إحياء الأرض", ["أ", "ب", "ج"], model="nano")

    assert scores == [0.3, 0.9, 0.0]
    call = model.calls[0]
    assert (call["stage"], call["model"], call["schema"]) == (AiStage.RERANK, "nano", LlmRanking)
    assert '"number": 3' in call["user"]


def small_model(client: Any, *, timeout: float = 2.0) -> LlmReranker:
    ticks = iter(range(0, 1000, 5))
    return LlmReranker(
        client, model="nano", timeout_seconds=timeout, clock=lambda: next(ticks) / 1000
    )


async def test_the_small_model_scores_the_head_and_names_itself():
    answer = {"passages": [{"number": 1, "relevance": 2}, {"number": 2, "relevance": 8}]}
    model = FakeModelClient(answers=[answer])

    outcome = await small_model(model).rerank("q", ["x" * (MAX_PASSAGE_CHARS + 9), "ب"])

    assert outcome == RerankOutcome([0.2, 0.8], "nano", 5)
    call = model.calls[0]
    assert (call["stage"], call["model"]) == (AiStage.RERANK, "nano")
    assert "x" * (MAX_PASSAGE_CHARS + 1) not in call["user"]


async def test_the_small_model_is_not_asked_about_nothing():
    model = FakeModelClient()

    assert await small_model(model).rerank("q", []) == RerankOutcome([], None, 0)
    assert model.calls == []


class SlowModel(FakeModelClient):
    async def chat_json(self, schema, **kwargs):  # type: ignore[override]
        await asyncio.sleep(1)
        return await super().chat_json(schema, **kwargs)


async def test_a_small_model_that_fails_or_is_slow_leaves_the_fused_order():
    failing = FakeModelClient(answers=[AiCallError(AiErrorCode.SERVER_ERROR, "down")])
    slow = SlowModel(answers=[{"passages": []}])

    failed = await small_model(failing).rerank("q", ["أ"])
    late = await small_model(slow, timeout=0.01).rerank("q", ["أ"])

    assert (failed.scores, failed.model, failed.error) == (None, None, "server_error")
    assert (late.scores, late.error) == (None, "timeout")


async def test_an_answer_that_carries_text_is_refused_and_never_returned():
    # The schema is closed: a model that adds a field, here one quoting a verse, is refused
    # whole, and neither its text nor its scores reach the scan.
    quoted = {"passages": [{"number": 1, "relevance": 9, "why": verse_text(30, 50)}]}
    reply = {
        "choices": [
            {
                "message": {"role": "assistant", "content": json.dumps(quoted, ensure_ascii=False)},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10},
    }
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, json=reply))
    )
    client = ProviderClient(
        AiProvider.OPENAI,
        OpenAISettings(api_key="sk-test"),
        http,
        timeout_seconds=5,
        max_retries=0,
        backoff_seconds=0,
    )

    outcome = await small_model(client).rerank("q", ["أ"])

    assert outcome.scores is None
    assert outcome.error == "invalid_output"
    assert verse_text(30, 50) not in repr(outcome)
