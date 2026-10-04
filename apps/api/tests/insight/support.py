"""
Scenes, model answers and stores for the insight engine tests.

The scenes are written here: descriptions of what a photo shows, in Arabic, the
way the scene analyzer writes them. They carry no scripture. Model answers are
the structured outputs the planner, the verifier and the composer return,
built as dictionaries; texts are referred to by label (Q1, H1) only.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import AiProvider
from src.pipeline.schemas import (
    BBox,
    EntityOrigin,
    EvidenceStatus,
    SceneAction,
    SceneAnalysis,
    SceneEntity,
    SceneRelation,
)
from src.services.masar_import import import_path
from src.services.ontology_import import load_ontology
from tests.retrieval.support import store_world
from tests.support_ontology import parsed_real_ontology, parsed_real_path


async def store_engine_world(session: AsyncSession) -> None:
    """The scripture fixtures, the real ontology and the real learning path."""
    await store_world(session)
    await load_ontology(session, parsed_real_ontology())
    await import_path(session, parsed_real_path(), source_file="masar.md", source_sha256="c" * 64)


def entity(
    entity_id: str,
    label: str,
    arabic: str,
    status: EvidenceStatus = EvidenceStatus.OBSERVED,
    bbox: BBox | None = None,
) -> SceneEntity:
    return SceneEntity(
        id=entity_id,
        label=label,
        label_arabic=arabic,
        bbox=bbox,
        origin=EntityOrigin.VLM,
        status=status,
    )


def scene(
    entities: list[SceneEntity],
    *,
    actions: list[SceneAction] | None = None,
    relations: list[SceneRelation] | None = None,
    description: str = "مطر خفيف يسقط على أرض متشققة فيها برك صغيرة.",
    question: str | None = None,
    sensitive: bool = False,
) -> SceneAnalysis:
    return SceneAnalysis(
        description=description,
        entities=entities,
        actions=actions or [],
        relations=relations or [],
        ambiguities=[],
        clarification_question=question,
        sensitive=["alcohol"] if sensitive else [],
        detector_available=False,
        unconfirmed_detection_ids=[],
        rejected=[],
        provider=AiProvider.OPENAI,
        model="fake-vision",
        prompt_version="scene@test",
    )


def rain_scene(**options: Any) -> SceneAnalysis:
    return scene(
        [
            entity("e1", "rain", "مطر", bbox=BBox(x=0.1, y=0.1, width=0.5, height=0.5)),
            entity("e2", "soil", "تربة"),
        ],
        **options,
    )


def planned(**fields: Any) -> dict[str, Any]:
    """One planned insight as the planner answers it, about the rain."""
    return {
        "title": "الحياة في قطرة",
        "glimpse": "كيف يعود الماء بالحياة إلى الأرض",
        "entity_ids": ["e1"],
        "action_ids": [],
        "concept": "إحياء الأرض",
        "value": "رحمة الله",
        "relation": "direct",
        "quran_queries": ["إحياء الأرض بالمطر"],
        "hadith_queries": ["الدعاء عند نزول المطر"],
        "ontology_entity_ids": ["E006"],
        "learning_unit_id": "T01_06",
        "content_level": "a",
        "visible_clues": ["قطرات على الأرض"],
        "limits": ["لا تثبت الصورة حال الأرض قبلها"],
    } | fields


def plan_answer(*insights: dict[str, Any], **fields: Any) -> dict[str, Any]:
    return {
        "insights": list(insights),
        "needs_clarification": False,
        "clarification_question": None,
        "unknown_concepts": [],
    } | fields


def verdict(
    label: str, *, relevant: bool = True, strength: str = "strong", relation: str = "direct"
) -> dict[str, Any]:
    return {
        "label": label,
        "relevant": relevant,
        "strength": strength,
        "relation": relation,
        "limit": "لا يثبت النص ما قبل الصورة",
    }


def verify_answer(*candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "candidates": [
            {"candidate": index, "texts": texts} for index, texts in enumerate(candidates)
        ]
    }


def composed(index: int = 0, **fields: Any) -> dict[str, Any]:
    return {
        "insight": index,
        "title": "الحياة في قطرة",
        "glimpse": "قطرة تعيد الحياة",
        "seen": "مطر خفيف على أرض متشققة",
        "value": "الرحمة التي تصل إلى الأرض",
        "quran": "تلفت الآية إلى أثر الرحمة في إحياء الأرض",
        "sunnah": "يضيف الحديث أدب الدعاء عند المطر",
        "life": "تأمل أثر الماء في يومك",
        "why_concept": "إحياء الأرض",
        "small_step": {
            "text": "ادعُ بالخير عند المطر",
            "kind": "text_grounded",
            "from_hadith": True,
        },
    } | fields


def compose_answer(*insights: dict[str, Any]) -> dict[str, Any]:
    return {"insights": list(insights)}
