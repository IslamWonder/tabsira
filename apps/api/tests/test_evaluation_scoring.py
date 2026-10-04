from __future__ import annotations

import pytest

from src.evaluation.scoring import iou, score_scene
from src.pipeline.schemas import (
    BBox,
    Detection,
    EntityOrigin,
    EvidenceStatus,
    ModerationStatus,
    SensitiveCategory,
    SensitivityResult,
)
from tests.evaluation_fixtures import (
    HALF,
    QUARTER,
    RULES,
    action,
    analysis,
    entity,
    gold_scene,
    relation,
)


def test_a_correct_analysis_scores_full_marks():
    scene = analysis(
        description="هاتف موضوع على دفتر مفتوح",
        entities=[entity("e1", "smartphone", "هاتف"), entity("e2", "notebook", "دفتر")],
        relations=[relation("ينظر إلى")],
        clarification_question="ماذا تفعل بالهاتف؟",
    )

    score = score_scene(scene, gold_scene(), RULES)

    assert (score.required_found, score.required_total) == (2, 2)
    assert score.missing_entities == []
    assert (score.expected_actions_found, score.expected_actions_total) == (1, 1)
    assert score.violations == 0
    assert score.sensitive_correct
    assert score.clarification_asked is True
    assert score.clarification_expected is True


def test_missing_entities_and_every_kind_of_violation_are_named():
    scene = analysis(
        description="طفلة تمسك شيئًا",
        entities=[entity("e1", "girl", "شخص"), entity("e2", "phone", "هاتف")],
        actions=[
            action("يصلي"),
            action("يقرأ الخبر"),
            action("يطعم القطة"),
            action("يطعم القطة بلطف", EvidenceStatus.INFERRED),
        ],
    )

    score = score_scene(scene, gold_scene(), RULES)

    assert score.missing_entities == ["دفتر"]
    assert score.expected_actions_found == 0
    assert score.forbidden_claims == [
        "praying: «يصلي»",
        "not in the image: «يقرا»",
        "reported as observed: «يطعم»",
    ]
    assert score.identity_inferences == ["girl", "طفله"]
    assert score.hallucinated_entities == ["شخص"]
    assert score.violations == 6


def test_arabic_fields_written_in_another_script_are_counted():
    scene = analysis(
        description="شجرة كبيرة" + "".join(chr(code) for code in range(0x5B64, 0x5B70)),
        entities=[entity("e1", "phone", "هاتف ذكي iPhone"), entity("e2", "pen", "قلم")],
        relations=[relation("holding by"), relation("فوق")],
    )

    score = score_scene(scene, gold_scene(), RULES)

    assert score.wrong_language == ["description", "relations.0.predicate"]
    assert score.violations == 2


def test_identity_words_are_whole_words():
    scene = analysis(description="قطة واقفة على أرجلها الأربع")

    assert score_scene(scene, gold_scene(), RULES).identity_inferences == []


def test_boxes_are_counted_dropped_and_compared_with_the_detector():
    detector_box = BBox(x=0.0, y=0.0, width=0.5, height=0.5)
    scene = analysis(
        entities=[
            entity(
                "e1",
                "phone",
                "هاتف",
                bbox=detector_box,
                origin=EntityOrigin.DETECTOR,
                detector_id="d1",
                model_bbox=QUARTER,
            ),
            entity("e2", "notebook", "دفتر", bbox=HALF, model_bbox=HALF),
            entity("e3", "pen", "قلم"),
        ],
        rejected=["entity e4: box outside the image", "action a1: no visible evidence"],
    )
    reference = [
        Detection(id="d1", label="x", label_arabic=None, confidence=0.9, bbox=HALF),
        Detection(
            id="d2",
            label="y",
            label_arabic=None,
            confidence=0.9,
            bbox=BBox(x=0.5, y=0.5, width=0.5, height=0.5),
        ),
    ]

    score = score_scene(scene, gold_scene(), RULES, reference)

    assert score.boxes_given == 3
    assert score.boxes_dropped == 1
    assert score.detector_ious == [0.5]
    assert score.reference_ious == [0.5, 1.0]
    assert score.rejected == 2
    assert score_scene(scene, gold_scene(), RULES).reference_ious == []


def test_the_guards_verdict_is_scored_when_there_is_one():
    flagged = analysis(sensitive=[SensitiveCategory.ALCOHOL])
    guarded = analysis(
        guard=SensitivityResult(
            sensitive=True,
            categories=[SensitiveCategory.VIOLENCE],
            scene_categories=[],
            moderation_categories=[SensitiveCategory.VIOLENCE],
            moderation_flags=["violence"],
            moderation_status=ModerationStatus.CHECKED,
        )
    )

    by_flags = score_scene(flagged, gold_scene(sensitive=True), RULES)
    by_guard = score_scene(guarded, gold_scene(), RULES)

    assert by_flags.sensitive_correct
    assert by_flags.categories == [SensitiveCategory.ALCOHOL]
    assert not by_guard.sensitive_correct
    assert by_guard.categories == [SensitiveCategory.VIOLENCE]


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        (HALF, HALF, 1.0),
        (HALF, QUARTER, 0.5),
        (HALF, BBox(x=0.5, y=0.5, width=0.5, height=0.5), 0.0),
        (BBox(x=0, y=0, width=0, height=0), BBox(x=0, y=0, width=0, height=0), 0.0),
    ],
)
def test_iou(first, second, expected):
    assert iou(first, second) == pytest.approx(expected)
