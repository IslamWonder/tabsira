"""
Scenes, model answers and stores for the insight engine tests.

The scenes are written here: descriptions of what a photo shows, in Arabic, the
way the scene analyzer writes them. They carry no scripture. Model answers are
the structured outputs the intent planner, the relevance verifier and the
composer return, built as dictionaries; texts are referred to by label (Q1, H1)
only. These are test cases: nothing here reaches a production prompt.
"""

from __future__ import annotations

import json
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


def queries(lexical: list[str] | None, semantic: list[str] | None) -> dict[str, list[str]]:
    return {"lexical": lexical or [], "semantic": semantic or []}


def intent(**fields: Any) -> dict[str, Any]:
    """One search intent as the planner answers it, about the rain."""
    return {
        "scene_anchor_ids": ["e1"],
        "observable_meaning": "مطر يسقط على أرض متشققة",
        "relation_description": None,
        "candidate_concept": "إحياء الأرض",
        "concept_basis": "الماء يصل أرضًا يابسة",
        "relation": "direct",
        "content_level": "a",
        "uncertainties": ["لا تظهر الصورة حال الأرض قبل المطر"],
        "unsupported_assumptions": [],
        "quran": queries(["إحياء الأرض بالمطر"], ["ينزل المطر فتحيا الأرض بعد يبسها"]),
        "hadith": queries(["الدعاء عند نزول المطر"], ["ما يقال عند نزول المطر"]),
        "ontology_entity_ids": ["E006"],
    } | fields


def plan_answer(*intents: dict[str, Any], **fields: Any) -> dict[str, Any]:
    return {
        "intents": list(intents),
        "needs_clarification": False,
        "clarification_question": None,
        "unknown_concepts": [],
    } | fields


def judged(
    label: str,
    *,
    accepted: bool = True,
    relation: str = "direct",
    reason: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """One text's judgement as the verifier answers it."""
    return {
        "label": label,
        "accepted": accepted,
        "relation": relation if accepted else "none",
        "basis_words": [1, 4] if accepted else [],
        "link": "يذكر النص إحياء الأرض بالماء" if accepted else "",
        "needed_context": None,
        "assumptions": [],
        "reject_reason": None if accepted else (reason or "meaning_not_supported"),
    } | fields


def verify_answer(
    texts: list[dict[str, Any]], pair: dict[str, Any] | str | None = "auto"
) -> dict[str, Any]:
    """A verifier answer; `pair` "auto" names the first accepted verse and hadith."""
    if pair == "auto":
        accepted = [t["label"] for t in texts if t["accepted"]]
        quran = next((label for label in accepted if label.startswith("Q")), None)
        hadith = next((label for label in accepted if label.startswith("H")), None)
        pair = (
            {"quran": quran, "hadith": hadith, "shared_meaning": "إحياء الأرض بالماء"}
            if quran or hadith
            else None
        )
    return {"texts": texts, "pair": pair}


def shown_labels(call: dict[str, Any]) -> list[str]:
    """The labels a verifier call was given."""
    return [text["label"] for text in json.loads(call["user"])["texts"]]


def accept_all(relation: str = "direct") -> Any:
    """A verifier that accepts every shortlisted text and pairs the first of each corpus."""

    def answer(call: dict[str, Any]) -> dict[str, Any]:
        return verify_answer([judged(label, relation=relation) for label in shown_labels(call)])

    return answer


def reject_all(call: dict[str, Any]) -> dict[str, Any]:
    return verify_answer(
        [judged(label, accepted=False, reason="lexical_overlap") for label in shown_labels(call)]
    )


def composed(**fields: Any) -> dict[str, Any]:
    return {
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
