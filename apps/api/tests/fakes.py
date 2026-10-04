"""A fake model client: stage tests mock the provider at the adapter boundary."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from src.ai.client import (
    ChatResult,
    EmbeddingResult,
    ModelClient,
    ModelImage,
    ModerationResult,
)
from src.ai.errors import AiCallError
from src.ai.records import CallKind, CallLog, CallRecord, Usage
from src.config import AiProvider, AiStage, OpenAISettings, OvhSettings, ProviderSettings


def make_record(
    provider: AiProvider = AiProvider.OVH,
    model: str = "fake-model",
    stage: AiStage = AiStage.VISION,
    kind: CallKind = CallKind.CHAT,
    *,
    latency_ms: int = 1200,
    usage: Usage | None = None,
    cost: float | None = 0.002,
    ok: bool = True,
) -> CallRecord:
    return CallRecord(
        provider=provider,
        model=model,
        stage=stage,
        kind=kind,
        started_at=datetime(2026, 10, 4, tzinfo=UTC),
        latency_ms=latency_ms,
        attempts=1,
        usage=usage or Usage(input_tokens=1000, output_tokens=300, reasoning_tokens=100),
        cost_usd=cost,
        ok=ok,
    )


Answer = BaseModel | dict[str, Any] | Exception
Moderation = tuple[bool, list[str]] | Exception


class FakeModelClient(ModelClient):
    """Answers chat calls from a queue (or a function of the call) and records every call."""

    def __init__(
        self,
        provider: AiProvider = AiProvider.OVH,
        settings: ProviderSettings | None = None,
        *,
        answers: Sequence[Answer] = (),
        moderations: Sequence[Moderation] = (),
        log: CallLog | None = None,
        latency_ms: int = 1200,
    ) -> None:
        self._provider = provider
        self._settings = settings or (
            OvhSettings(vision_model="fake-vision")
            if provider == AiProvider.OVH
            else OpenAISettings(vision_model="fake-vision", guard_model="omni-moderation-latest")
        )
        self.answers = list(answers)
        self.moderations = list(moderations)
        self.calls: list[dict[str, Any]] = []
        self.moderated: list[ModelImage] = []
        self.log = log
        self.latency_ms = latency_ms

    @property
    def provider(self) -> AiProvider:
        return self._provider

    @property
    def settings(self) -> ProviderSettings:
        return self._settings

    def _record(self, stage: AiStage, kind: CallKind, model: str, *, ok: bool) -> CallRecord:
        record = make_record(self._provider, model, stage, kind, latency_ms=self.latency_ms, ok=ok)
        if self.log is not None:
            self.log.add(record)
        return record

    async def chat_json[T: BaseModel](
        self,
        schema: type[T],
        *,
        stage: AiStage,
        system: str,
        user: str,
        images: Sequence[ModelImage] = (),
        model: str | None = None,
        max_output_tokens: int = 4096,
        temperature: float | None = None,
        reasoning_effort: str | None = None,
    ) -> ChatResult[T]:
        self.calls.append(
            {
                "schema": schema,
                "stage": stage,
                "system": system,
                "user": user,
                "images": list(images),
                "model": model,
                "max_output_tokens": max_output_tokens,
            }
        )
        chosen = model or self._settings.model_for(stage)
        answer = self.answers.pop(0)
        if isinstance(answer, AiCallError):
            raise AiCallError(
                answer.code,
                str(answer),
                record=self._record(stage, CallKind.CHAT, chosen, ok=False),
            )
        if isinstance(answer, Exception):
            raise answer
        value = schema.model_validate(
            answer.model_dump() if isinstance(answer, BaseModel) else answer
        )
        return ChatResult(value=value, record=self._record(stage, CallKind.CHAT, chosen, ok=True))

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
        dimensions: int | None = None,
    ) -> EmbeddingResult:
        raise NotImplementedError

    async def moderate_image(
        self, image: ModelImage, *, model: str | None = None
    ) -> ModerationResult:
        self.moderated.append(image)
        verdict = self.moderations.pop(0)
        if isinstance(verdict, Exception):
            raise verdict
        flagged, categories = verdict
        chosen = model or self._settings.model_for(AiStage.GUARD)
        record = self._record(AiStage.GUARD, CallKind.MODERATION, chosen, ok=True)
        return ModerationResult(
            flagged=flagged,
            categories=categories,
            scores=dict.fromkeys(categories, 0.9),
            record=record,
        )
