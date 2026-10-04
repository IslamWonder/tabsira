"""
A small scripture store for the retrieval tests, and a model client that embeds.

The store is the scripture fixtures (real rows, never typed by hand): the
quranpedia verses with their annotations, the hadiths of five books and the
Sunnah signals that link to two of them. Vectors are made up by `fake_vector`,
a deterministic function of the text, so a test can place a query next to the
document it wants found without any model.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.client import EmbeddingResult
from src.ai.errors import AiCallError, AiErrorCode
from src.ai.records import CallKind, Usage
from src.config import AiProvider, AiStage, OpenAISettings, OvhSettings
from src.scripture.annotations import import_annotations
from src.scripture.sunnah import import_signals, repair
from tests.fakes import FakeModelClient, make_record
from tests.scripture.fixtures import load_json, store_hadiths, store_quran


async def store_world(session: AsyncSession) -> None:
    """Import every scripture fixture as the importers do, annotations and signals included."""
    await store_quran(session)
    await import_annotations(session, load_json("quran-annotations.json"), "a" * 64)
    await store_hadiths(session)
    records = repair(load_json("sunnah-enriched.json")["results"])
    await import_signals(session, records, model="m", source_sha256="b" * 64)


def fake_vector(text: str, dimensions: int = 8) -> list[float]:
    """A unit vector made from the text's hash: equal texts meet, others scatter."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    raw = [digest[index] - 127.5 for index in range(dimensions)]
    norm = math.sqrt(sum(value * value for value in raw))
    return [value / norm for value in raw]


class EmbeddingClient(FakeModelClient):
    """A fake client whose `embed` answers with `fake_vector`, or with a scripted failure."""

    def __init__(
        self,
        provider: AiProvider = AiProvider.OPENAI,
        *,
        dimensions: int = 8,
        cost_per_call: float = 0.01,
        fail_on_call: int | None = None,
        vector_for: Callable[[str], list[float]] | None = None,
    ) -> None:
        settings = (
            OpenAISettings(embedding_model="fake-embed", api_key="k")
            if provider is AiProvider.OPENAI
            else OvhSettings(embedding_model="fake-embed", api_key="k")
        )
        super().__init__(provider, settings)
        self.dimensions = dimensions
        self.cost_per_call = cost_per_call
        self.fail_on_call = fail_on_call
        self.vector_for = vector_for
        self.embedded: list[list[str]] = []

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
        dimensions: int | None = None,
    ) -> EmbeddingResult:
        self.embedded.append(list(texts))
        if self.fail_on_call is not None and len(self.embedded) == self.fail_on_call:
            raise AiCallError(AiErrorCode.TIMEOUT, "the provider did not answer in time")
        size = dimensions or self.dimensions
        vectors = [
            self.vector_for(text) if self.vector_for else fake_vector(text, size) for text in texts
        ]
        record = make_record(
            self.provider,
            model or "fake-embed",
            AiStage.EMBEDDING,
            CallKind.EMBEDDING,
            latency_ms=120,
            usage=Usage(input_tokens=10 * len(texts)),
            cost=self.cost_per_call,
        )
        return EmbeddingResult(vectors=vectors, record=record)
