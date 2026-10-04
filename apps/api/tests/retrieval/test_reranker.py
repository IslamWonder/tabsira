from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from src.config import AiStage
from src.retrieval.reranker import (
    MAX_PASSAGE_CHARS,
    MAX_PASSAGES,
    LlmRanking,
    RerankerClient,
    llm_rerank,
)
from tests.fakes import FakeModelClient


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
