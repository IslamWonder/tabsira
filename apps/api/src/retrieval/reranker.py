"""
Rerank the fused candidates: the cross-encoder of services/vision, or a language model.

`RerankerClient` calls `POST /rerank` on the vision service, which reads the
query and each candidate's document together and scores how well they match
(master prompt v2 §9). A scan never waits on it: a service that is down, slow,
or answers nonsense is skipped, and the outcome says so (`scores` None with
the reason); the caller then keeps the fused order and records why.

`llm_rerank` asks a chat model to score the same pairs. It is the baseline the
retrieval benchmark measures the cross-encoder against (an LLM rerank was the
slowest stage of the earlier build); the pipeline does not use it.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Annotated

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.ai.client import ModelClient
from src.config import AiStage

log = logging.getLogger("tabsira.retrieval.reranker")

# The service refuses more passages, and longer ones (services/vision/src/vision/config.py).
MAX_PASSAGES = 64
MAX_PASSAGE_CHARS = 4000


@dataclass(frozen=True, slots=True)
class RerankOutcome:
    """Scores in passage order, or None with the reason the reranker was skipped."""

    scores: list[float] | None
    model: str | None
    latency_ms: int
    error: str | None = None


class _Answer(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scores: list[float]
    model: str
    ms: int


class RerankerClient:
    """Calls `POST /rerank` on the vision service."""

    def __init__(
        self,
        base_url: str,
        http: httpx.AsyncClient,
        *,
        timeout_seconds: float,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._url = base_url.rstrip("/") + "/rerank"
        self._http = http
        self._timeout = timeout_seconds
        self._clock = clock

    async def rerank(self, query: str, passages: Sequence[str]) -> RerankOutcome:
        started = self._clock()
        if not passages:
            return RerankOutcome([], None, 0)
        sent = [passage[:MAX_PASSAGE_CHARS] for passage in passages[:MAX_PASSAGES]]
        answer = await self._ask(query, sent)
        if isinstance(answer, str):
            log.warning("reranker skipped: %s", answer)
            return RerankOutcome(None, None, self._elapsed(started), answer)
        return RerankOutcome(answer.scores, answer.model, self._elapsed(started))

    async def _ask(self, query: str, passages: list[str]) -> _Answer | str:
        """Return the service's answer, or the reason there is none."""
        body = {"query": query, "passages": passages}
        try:
            response = await self._http.post(self._url, json=body, timeout=self._timeout)
        except httpx.TimeoutException:
            return "timeout"
        except httpx.TransportError:
            return "unreachable"
        if response.status_code != httpx.codes.OK:
            return f"http_{response.status_code}"
        try:
            answer = _Answer.model_validate_json(response.content)
        except ValidationError:
            return "invalid_response"
        return answer if len(answer.scores) == len(passages) else "invalid_response"

    def _elapsed(self, started: float) -> int:
        return round((self._clock() - started) * 1000)


class _Judged(BaseModel):
    """The relevance of one numbered passage to the query, from 0 (none) to 10 (direct)."""

    number: int
    relevance: Annotated[int, Field(ge=0, le=10)]


class LlmRanking(BaseModel):
    """A relevance score for every numbered passage."""

    passages: list[_Judged]


LLM_RERANK_SYSTEM = (
    "You rank search results for an Arabic app about the Quran and the Sunnah. "
    "Given a concept query and numbered passages (folded Arabic text followed by topic "
    "keywords), give every passage a relevance from 0 (unrelated) to 10 (states the concept "
    "directly). Judge meaning, not shared words. Answer with the numbers only; never copy "
    "or quote any passage."
)


async def llm_rerank(
    client: ModelClient, query: str, passages: Sequence[str], *, model: str | None = None
) -> list[float]:
    """Score each passage with a chat model; a passage it left out scores 0."""
    listing = json.dumps(
        [{"number": index, "passage": text} for index, text in enumerate(passages, start=1)],
        ensure_ascii=False,
    )
    result = await client.chat_json(
        LlmRanking,
        stage=AiStage.RERANK,
        system=LLM_RERANK_SYSTEM,
        user=f"Query: {query}\nPassages: {listing}",
        model=model,
        max_output_tokens=2048,
    )
    scores = [0.0] * len(passages)
    for judged in result.value.passages:
        if 1 <= judged.number <= len(passages):
            scores[judged.number - 1] = judged.relevance / 10
    return scores
