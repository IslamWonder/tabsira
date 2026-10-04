"""Small builders of scenes, engine results and scan rows for the scan workflow tests."""

from __future__ import annotations

from typing import Any

from src.config import AiProvider
from src.models import Insight, InsightOrigin, Scan, ScanSource, ScanStatus
from src.owner import Owner
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
from src.pipeline.schemas import (
    BBox,
    EntityOrigin,
    EvidenceStatus,
    SceneAnalysis,
    SceneEntity,
)

LEAF = BBox(x=0.1, y=0.2, width=0.3, height=0.2)


def entity(identifier: str = "e1", label: str = "نبتة", box: BBox | None = LEAF) -> SceneEntity:
    return SceneEntity(
        id=identifier,
        label="plant",
        label_arabic=label,
        bbox=box,
        origin=EntityOrigin.VLM,
        status=EvidenceStatus.OBSERVED,
    )


def scene(*entities: SceneEntity, **values: Any) -> SceneAnalysis:
    defaults: dict[str, Any] = {
        "description": "نبتة صغيرة تحت المطر",
        "entities": list(entities) if entities else [entity()],
        "actions": [],
        "relations": [],
        "ambiguities": [],
        "clarification_question": None,
        "sensitive": [],
        "detector_available": False,
        "unconfirmed_detection_ids": [],
        "rejected": [],
        "provider": AiProvider.OVH,
        "model": "fake-vision",
        "prompt_version": "test",
    }
    return SceneAnalysis(**(defaults | values))


def quran(surah: int = 30, ayah: int = 50, **values: Any) -> EvidenceRef:
    return EvidenceRef(
        ref=QuranRef(surah=surah, ayah=ayah),
        relation=values.get("relation", RelationType.DIRECT),
        retrieval_score=0.8,
        matched_on=values.get("matched_on", "إحياء الأرض"),
    )


def hadith(collection: str = "bukhari", number: str = "1032", **values: Any) -> EvidenceRef:
    return EvidenceRef(
        ref=HadithRef(collection=collection, number=number),
        relation=values.get("relation", RelationType.ACTION_BASED),
        retrieval_score=0.7,
        rerank_score=0.9,
        matched_on=values.get("matched_on", "رؤية المطر"),
    )


def proposed(**values: Any) -> ProposedInsight:
    defaults: dict[str, Any] = {
        "title": "الحياة في قطرة",
        "glimpse": "الماء سبب للحياة",
        "entity_ids": ["e1"],
        "anchor": None,
        "relation": RelationType.DIRECT,
        "quran": quran(),
        "hadith": hadith(),
        "explanation": [
            ExplanationPart(section="seen", text="قطرات على ورق نبتة."),
            ExplanationPart(section="quran", text="تدعو الآية إلى النظر في أثر الرحمة."),
        ],
        "why": WhyThis(
            visible_clues=["قطرات الماء"], concept="الإحياء", limits=["الصورة لا تثبت كل شيء."]
        ),
        "small_step": SmallStep(
            text="احفظ الدعاء الوارد في الحديث.",
            kind="text_grounded",
            grounded_in=["hadith:bukhari:1032"],
        ),
        "learning_unit_id": "T01_06",
        "learning_path_version": "tabsira-masar-1.0",
    }
    return ProposedInsight(**(defaults | values))


def scan_row(owner: Owner, **values: Any) -> Scan:
    defaults: dict[str, Any] = {
        "source": ScanSource.UPLOAD,
        "status": ScanStatus.QUEUED,
        "engine": "pipeline",
        "image_width": 96,
        "image_height": 64,
    }
    return Scan(**owner.columns(), **(defaults | values))


def insight_row(owner: Owner, **values: Any) -> Insight:
    defaults: dict[str, Any] = {
        "origin": InsightOrigin.SCAN,
        "engine": "pipeline",
        "title": "الحياة في قطرة",
        "glimpse": "الماء سبب للحياة",
        "relation": "direct",
        "quran_surah": 30,
        "quran_ayah": 50,
        "quran_evidence": {"relation": "direct", "matched_on": "إحياء الأرض"},
        "hadith_collection": "bukhari",
        "hadith_number": "1032",
        "hadith_evidence": {"relation": "action_based", "matched_on": "رؤية المطر"},
        "explanation": [{"section": "seen", "text": "قطرات على ورق نبتة.", "sources": []}],
        "why": {"visible_clues": ["قطرات"], "concept": "الإحياء", "limits": []},
        "small_step": {
            "text": "احفظ الدعاء الوارد في الحديث.",
            "kind": "text_grounded",
            "grounded_in": ["hadith:bukhari:1032"],
        },
        "learning_unit_id": "T01_06",
        "learning_path_version": "tabsira-masar-1.0",
    }
    return Insight(**owner.columns(), **(defaults | values))
