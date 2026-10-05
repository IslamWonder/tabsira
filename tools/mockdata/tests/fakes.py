"""Fakes for the process step: a model client, scenes, insights and a photo. No network."""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from PIL import Image
from pydantic import BaseModel
from src.ai.client import ChatResult, EmbeddingResult, ModelClient, ModelImage, ModerationResult
from src.ai.errors import AiCallError
from src.ai.records import CallKind, CallLog, CallRecord, Usage
from src.config import AiProvider, AiStage, OvhSettings, ProviderSettings, Settings
from src.pipeline.engine import (
    EvidenceRef,
    ExplanationPart,
    HadithRef,
    ProposedInsight,
    QuranRef,
    RelationType,
    SmallStep,
    WhyThis,
)
from src.pipeline.schemas import EntityOrigin, EvidenceStatus, SceneAnalysis, SceneEntity

TEST_DATABASE = "postgresql+asyncpg://u:p@127.0.0.1:5432/mock_test"


def settings(**values: Any) -> Settings:
    return Settings(_env_file=None, database_url=TEST_DATABASE, **values)


def record(
    *,
    provider: AiProvider = AiProvider.OVH,
    model: str = "fake-model",
    ok: bool = True,
    cost: float | None = 0.001,
) -> CallRecord:
    return CallRecord(
        provider=provider,
        model=model,
        stage=AiStage.CHAT,
        kind=CallKind.CHAT,
        started_at=datetime(2026, 10, 5, tzinfo=UTC),
        latency_ms=10,
        attempts=1,
        usage=Usage(input_tokens=100, output_tokens=20),
        cost_usd=cost,
        ok=ok,
    )


class FakeClient(ModelClient):
    """Answers chat calls from a queue and records each call; embeds and moderates nothing."""

    def __init__(
        self,
        answers: Sequence[BaseModel | dict[str, Any] | Exception] = (),
        *,
        provider: AiProvider = AiProvider.OVH,
        log: CallLog | None = None,
    ) -> None:
        self.answers = list(answers)
        self.calls: list[dict[str, Any]] = []
        self._provider = provider
        self._settings: ProviderSettings = OvhSettings()
        self.log = log

    @property
    def provider(self) -> AiProvider:
        return self._provider

    @property
    def settings(self) -> ProviderSettings:
        return self._settings

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
            {"stage": stage, "system": system, "user": user, "model": model, "images": images}
        )
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        made = record(model=model or "fake-model")
        if self.log is not None:
            self.log.add(made)
        data = answer.model_dump() if isinstance(answer, BaseModel) else answer
        return ChatResult(value=schema.model_validate(data), record=made)

    async def embed(
        self, texts: Sequence[str], *, model: str | None = None, dimensions: int | None = None
    ) -> EmbeddingResult:
        self.calls.append({"embed": list(texts), "model": model, "dimensions": dimensions})
        return EmbeddingResult(vectors=[[0.0]], record=record())

    async def moderate_image(
        self, image: ModelImage, *, model: str | None = None
    ) -> ModerationResult:
        self.calls.append({"moderate_image": image, "model": model})
        return ModerationResult(flagged=False, categories=[], scores={}, record=record())

    async def moderate_text(self, text: str, *, model: str | None = None) -> ModerationResult:
        self.calls.append({"moderate_text": text, "model": model})
        return ModerationResult(flagged=False, categories=[], scores={}, record=record())


def failure(code: str = "timeout", *, with_record: bool = True) -> AiCallError:
    from src.ai.errors import AiErrorCode

    return AiCallError(
        AiErrorCode(code), "failed", record=record(ok=False) if with_record else None
    )


def entity(label: str = "cat", arabic: str = "قطة", entity_id: str = "e1") -> SceneEntity:
    return SceneEntity(
        id=entity_id,
        label=label,
        label_arabic=arabic,
        bbox=None,
        origin=EntityOrigin.VLM,
        status=EvidenceStatus.OBSERVED,
    )


def scene(
    *,
    description: str = "قطة تجلس على نافذة",
    entities: Sequence[SceneEntity] | None = None,
    rejected: Sequence[str] = (),
    sensitive: bool = False,
) -> SceneAnalysis:
    from src.pipeline.schemas import SensitiveCategory

    return SceneAnalysis(
        description=description,
        entities=list(entities if entities is not None else [entity()]),
        actions=[],
        relations=[],
        ambiguities=[],
        clarification_question=None,
        sensitive=[SensitiveCategory.ALCOHOL] if sensitive else [],
        detector_available=True,
        unconfirmed_detection_ids=[],
        rejected=list(rejected),
        provider=AiProvider.OVH,
        model="fake-vision",
        prompt_version="v1+v1",
    )


def insight(
    *,
    quran: bool = True,
    hadith: bool = True,
    step: bool = True,
    seen: str = "قطة على النافذة",
    clues: Sequence[str] = ("قطة",),
) -> ProposedInsight:
    return ProposedInsight(
        title="سكينة القطة",
        glimpse="هدوء يدعو إلى التأمل",
        entity_ids=["e1"],
        anchor=None,
        relation=RelationType.CLOSE_CONCEPTUAL,
        quran=EvidenceRef(
            ref=QuranRef(surah=2, ayah=164),
            relation=RelationType.CLOSE_CONCEPTUAL,
            retrieval_score=0.5,
            matched_on="التفكر",
        )
        if quran
        else None,
        hadith=EvidenceRef(
            ref=HadithRef(collection="bukhari", number="1"),
            relation=RelationType.THEMATIC_REMINDER,
            retrieval_score=0.4,
            matched_on="الرفق",
        )
        if hadith
        else None,
        explanation=[
            ExplanationPart(section="seen", text=seen),
            ExplanationPart(section="value", text="الرفق بالحيوان"),
        ],
        why=WhyThis(visible_clues=list(clues), concept="الرفق", limits=["لا نعرف صاحبها"]),
        small_step=SmallStep(text="أطعم قطة اليوم", kind="reflection") if step else None,
    )


def jpeg(width: int = 64, height: int = 64) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "orange").save(buffer, format="JPEG")
    return buffer.getvalue()
