from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config import AiProvider
from src.pipeline.engine import (
    EngineRequest,
    EngineResult,
    EngineStage,
    EngineStatus,
    EvidenceRef,
    ExplanationPart,
    HadithRef,
    LearnerContext,
    ProposedInsight,
    QuranRef,
    RelationType,
    WhyThis,
)
from src.pipeline.schemas import SceneAnalysis


def scene() -> SceneAnalysis:
    return SceneAnalysis(
        description="نبتة صغيرة تحت المطر",
        entities=[],
        actions=[],
        relations=[],
        ambiguities=[],
        clarification_question=None,
        sensitive=[],
        detector_available=False,
        unconfirmed_detection_ids=[],
        rejected=[],
        provider=AiProvider.OPENAI,
        model="m",
        prompt_version="v",
    )


def test_evidence_is_carried_by_reference_and_told_apart_by_its_kind():
    quran = EvidenceRef.model_validate(
        {
            "ref": {"kind": "quran", "surah": 30, "ayah": 50},
            "relation": "direct",
            "retrieval_score": 0.8,
            "matched_on": "إحياء الأرض",
        }
    )
    hadith = EvidenceRef.model_validate(
        {
            "ref": {"kind": "hadith", "collection": "bukhari", "number": "1032"},
            "relation": "action_based",
            "retrieval_score": 0.7,
            "rerank_score": 0.9,
            "matched_on": "رؤية المطر",
        }
    )

    assert quran.ref == QuranRef(surah=30, ayah=50)
    assert hadith.ref == HadithRef(collection="bukhari", number="1032")
    assert quran.rerank_score is None


def test_a_reference_outside_the_mushaf_is_refused():
    with pytest.raises(ValidationError):
        QuranRef(surah=115, ayah=1)


def test_a_proposed_insight_holds_no_scripture_text_field():
    insight = ProposedInsight(
        title="الحياة في قطرة",
        glimpse="كيف تُحيا الأرض بعد موتها",
        entity_ids=["e1"],
        anchor=None,
        relation=RelationType.DIRECT,
        quran=None,
        hadith=None,
        explanation=[ExplanationPart(section="value", text="شرح")],
        why=WhyThis(visible_clues=["قطرات على الورق"], concept="الإحياء"),
    )

    assert "text" not in ProposedInsight.model_fields
    assert insight.small_step is None
    assert insight.explanation[0].sources == []


def test_a_request_carries_the_learner_context_apart_from_the_scene():
    request = EngineRequest(scan_id="s1", scene=scene())

    assert request.learner == LearnerContext()
    assert request.learner.religious_background == "unknown"
    assert request.max_insights == 3


def test_a_result_reports_its_status_stages_and_awaited_rulings():
    result = EngineResult(
        status=EngineStatus.NO_RELEVANT_EVIDENCE,
        awaiting_ruling=[HadithRef(collection="muslim", number="8")],
        stage_ms={EngineStage.SEARCHING: 120},
    )

    assert result.insights == []
    assert result.stage_ms[EngineStage.SEARCHING] == 120
