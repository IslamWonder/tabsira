from __future__ import annotations

import json
import math
from typing import Any

import pytest

from src.ai.errors import AiCallError, AiErrorCode
from src.config import AiProvider, AiStage, BoxCoordinates, OvhSettings
from src.pipeline.leak_guard import LeakGuard, ScriptureLeakError
from src.pipeline.prompt import load_prompt
from src.pipeline.scene_analyzer import (
    MAX_ACTIONS,
    MAX_ENTITIES,
    MAX_RELATIONS,
    SceneModelOutput,
    analyze_scene,
    build_scene,
    from_ratio_box,
    scene_texts,
    to_ratio_box,
)
from src.pipeline.schemas import (
    BBox,
    Detection,
    DetectorResult,
    EncodedImage,
    EntityOrigin,
    EvidenceStatus,
    SceneRequest,
    SensitiveCategory,
)
from tests.fakes import FakeModelClient

IMAGE = EncodedImage(data=b"jpeg", width=1344, height=768)
PHONE = Detection(
    id="d1",
    label="smartphone",
    label_arabic="هاتف ذكي",
    confidence=0.756,
    bbox=BBox(x=0.25, y=0.25, width=0.5, height=0.5),
)
TABLE = Detection(
    id="d2",
    label="table",
    label_arabic=None,
    confidence=0.4,
    bbox=BBox(x=0, y=0, width=1, height=1),
)
DETECTOR = DetectorResult(available=True, detections=[PHONE, TABLE], latency_ms=900)


def entity(identifier: str, **values: Any) -> dict[str, Any]:
    return {
        "id": identifier,
        "label": "Smartphone",
        "label_arabic": " هاتف ",
        "detector_id": None,
        "box": None,
        "status": "observed",
        **values,
    }


def output(**values: Any) -> dict[str, Any]:
    return {
        "description": " هاتف موضوع على دفتر مفتوح فوق مكتب خشبي. ",
        "entities": [entity("e1", detector_id="d1", box=[300, 200, 1000, 580])],
        "actions": [],
        "relations": [],
        "ambiguities": ["لا يظهر ما يُستعمل له الهاتف", "  "],
        "clarification_question": "ماذا تفعل بالهاتف؟",
        "sensitive": [],
        **values,
    }


def build(answer: dict[str, Any], coordinates: BoxCoordinates = BoxCoordinates.PIXELS, **request):
    return build_scene(
        SceneModelOutput.model_validate(answer),
        SceneRequest(image=IMAGE, detector=request.get("detector", DETECTOR)),
        coordinates,
        provider=AiProvider.OVH,
        model="m",
        prompt_version="v",
    )


# ─── The call ──────────────────────────────────────────────────────


async def test_the_model_sees_the_image_and_the_boxes_in_the_stated_pixels():
    settings = OvhSettings(vision_model="fake-vision", box_coordinates="pixels")
    client = FakeModelClient(settings=settings, answers=[output()])

    scene = await analyze_scene(SceneRequest(image=IMAGE, detector=DETECTOR), client=client)

    call = client.calls[0]
    assert call["schema"] is SceneModelOutput
    assert call["stage"] is AiStage.VISION
    assert call["system"] == load_prompt("scene_analyzer_system.v2").text
    assert call["images"][0].data == b"jpeg"
    assert call["max_output_tokens"] == 8192
    user = call["user"]
    assert "The photo is 1344 pixels wide and 768 pixels high." in user
    assert "pixels of this photo: x from 0 (left edge) to 1344 (right edge)" in user
    lines = user.split("may be wrong:\n")[1].split("\n\n")[0].splitlines()
    assert [json.loads(line) for line in lines] == [
        {
            "id": "d1",
            "label": "smartphone",
            "label_arabic": "هاتف ذكي",
            "confidence": 0.76,
            "box": [336, 192, 1008, 576],
        },
        {
            "id": "d2",
            "label": "table",
            "label_arabic": None,
            "confidence": 0.4,
            "box": [0, 0, 1344, 768],
        },
    ]
    assert scene.provider is AiProvider.OVH
    assert scene.model == "fake-vision"
    assert scene.prompt_version.startswith("scene_analyzer_system.v2@")
    assert "+scene_analyzer_user.v1@" in scene.prompt_version


async def test_a_qwen_provider_is_asked_for_the_0_1000_grid():
    settings = OvhSettings(vision_model="Qwen3.8-27B", box_coordinates="thousandths")
    client = FakeModelClient(settings=settings, answers=[output()])

    scene = await analyze_scene(SceneRequest(image=IMAGE, detector=DETECTOR), client=client)

    user = client.calls[0]["user"]
    assert "a 0-1000 grid on each axis" in user
    assert '"box": [250, 250, 750, 750]' in user
    # The model's own box is read on the same grid: [300, 200, 1000, 580] of 1000.
    assert scene.entities[0].model_bbox == BBox(x=0.3, y=0.2, width=0.7, height=0.38)


@pytest.mark.parametrize(
    ("detector", "expected"),
    [
        (DetectorResult(available=False, latency_ms=1, error="timeout"), "not available"),
        (DetectorResult(available=True, latency_ms=1), "it found nothing"),
    ],
)
async def test_the_prompt_says_when_there_are_no_boxes(detector, expected):
    client = FakeModelClient(answers=[output(entities=[entity("e1")])])

    scene = await analyze_scene(SceneRequest(image=IMAGE, detector=detector), client=client)

    assert f"Detector: {expected}" in client.calls[0]["user"]
    assert scene.detector_available is detector.available


async def test_a_failed_call_is_not_hidden():
    client = FakeModelClient(answers=[AiCallError(AiErrorCode.TIMEOUT, "slow")])

    with pytest.raises(AiCallError):
        await analyze_scene(SceneRequest(image=IMAGE, detector=DETECTOR), client=client)


async def test_scripture_in_any_field_refuses_the_whole_scene():
    marked = "مطر" + chr(0x06D6)
    client = FakeModelClient(answers=[output(ambiguities=[marked])])

    with pytest.raises(ScriptureLeakError) as caught:
        await analyze_scene(SceneRequest(image=IMAGE, detector=DETECTOR), client=client)

    assert list(caught.value.fields) == ["ambiguities.0"]


async def test_a_custom_guard_is_used():
    client = FakeModelClient(answers=[output()])

    class Refuse(LeakGuard):
        def ensure_clean(self, fields):
            raise ScriptureLeakError({})

    with pytest.raises(ScriptureLeakError):
        await analyze_scene(
            SceneRequest(image=IMAGE, detector=DETECTOR), client=client, guard=Refuse()
        )


def test_the_profile_never_reaches_this_stage():
    assert set(SceneRequest.model_fields) == {"image", "detector"}


# ─── Entities and boxes ────────────────────────────────────────────


def test_a_matched_detection_keeps_its_box_and_takes_the_models_label():
    scene = build(output())

    (phone,) = scene.entities
    assert phone.label == "smartphone"
    assert phone.label_arabic == "هاتف"
    assert phone.origin is EntityOrigin.DETECTOR
    assert phone.detector_id == "d1"
    assert phone.bbox == PHONE.bbox
    assert phone.model_bbox == BBox(x=0.2232, y=0.2604, width=0.5208, height=0.4948)
    assert phone.status is EvidenceStatus.OBSERVED
    assert scene.unconfirmed_detection_ids == ["d2"]
    assert scene.rejected == []
    assert scene.description == "هاتف موضوع على دفتر مفتوح فوق مكتب خشبي."
    assert scene.ambiguities == ["لا يظهر ما يُستعمل له الهاتف"]


def test_a_person_named_by_gender_age_or_religion_becomes_a_person_and_is_recorded():
    """v2 §0.6, §6: no inference of religion, age or gender about anyone in the photo."""
    scene = build(
        output(
            description="امرأة محجبة تحمل طفلًا بجانب رجل عجوز، وقطة على السجادة.",
            entities=[
                entity("e1", label="muslim woman", label_arabic="امرأة محجبة"),
                entity("e2", label="old man", label_arabic="رجل عجوز"),
                entity("e3", label="cat", label_arabic="قطة"),
                entity("e4", label="prayer rug", label_arabic="سجادة"),
            ],
            actions=[
                action("a1", label="تحمل الطفل", visible_evidence=["يد المرأة حول الرضيع"]),
            ],
            relations=[
                {
                    "subject_id": "e1",
                    "predicate": "بجانب الرجل",
                    "object_id": "e2",
                    "evidence": "الشيخ واقف",
                }
            ],
            ambiguities=["لا يظهر إن كان الولد نائمًا", "لا يظهر ما على السجادة"],
            clarification_question="هل الطفل يبكي؟",
        )
    )

    assert scene.description == "شخص شخص تحمل شخص بجانب شخص شخص، وقطة على السجادة."
    assert [(e.label, e.label_arabic) for e in scene.entities] == [
        ("person", "شخص"),
        ("person", "شخص"),
        ("cat", "قطة"),
        ("prayer rug", "سجادة"),
    ]
    (action_kept,) = scene.actions
    assert (action_kept.label, action_kept.visible_evidence) == (
        "تحمل الشخص",
        ["يد الشخص حول الشخص"],
    )
    (relation,) = scene.relations
    assert (relation.predicate, relation.evidence) == ("بجانب الشخص", "الشخص واقف")
    assert scene.ambiguities == ["لا يظهر إن كان الشخص نائمًا", "لا يظهر ما على السجادة"]
    assert scene.clarification_question == "هل الشخص يبكي؟"
    assert scene.rejected == [
        "entity e1 label: person descriptor replaced by 'person': muslim, woman",
        "entity e1 label_arabic: person descriptor replaced by «شخص»: امرأة, محجبة",
        "entity e2 label: person descriptor replaced by 'person': old, man",
        "entity e2 label_arabic: person descriptor replaced by «شخص»: رجل, عجوز",
        "action a1 label: person descriptor replaced by «شخص»: الطفل",
        "action a1 evidence: person descriptor replaced by «شخص»: المرأة, الرضيع",
        "relation e1-e2 predicate: person descriptor replaced by «شخص»: الرجل",
        "relation e1-e2 evidence: person descriptor replaced by «شخص»: الشيخ",
        "description: person descriptor replaced by «شخص»: امرأة, محجبة, طفلا, رجل, عجوز",
        "ambiguities.0: person descriptor replaced by «شخص»: الولد",
        "clarification_question: person descriptor replaced by «شخص»: الطفل",
    ]
    # No descriptor is left in any text the later stages read.
    for text in scene_texts(scene).values():
        assert not {"امرأة", "محجبة", "طفل", "رجل", "عجوز", "الشيخ", "الولد"} & set(text.split())


def test_an_entity_the_detector_missed_keeps_the_models_converted_box():
    scene = build(output(entities=[entity("e1", box=[0, 384, 672, 768], status="inferred")]))

    (thing,) = scene.entities
    assert thing.origin is EntityOrigin.VLM
    assert thing.bbox == BBox(x=0.0, y=0.5, width=0.5, height=0.5)
    assert thing.status is EvidenceStatus.INFERRED
    assert scene.unconfirmed_detection_ids == ["d1", "d2"]


def test_a_box_outside_the_image_is_dropped_and_recorded():
    # A 0-1000 answer read as pixels of a 768-high photo: y reaches 998.
    scene = build(output(entities=[entity("e1", box=[556, 752, 865, 998])]))

    assert scene.entities[0].bbox is None
    assert scene.entities[0].model_bbox is None
    assert scene.rejected == ["entity e1: box outside the image"]


def test_one_detection_matches_one_entity_and_unknown_detections_are_refused():
    scene = build(
        output(
            entities=[
                entity("e1", detector_id="d1"),
                entity("e2", detector_id="d1"),
                entity("e3", detector_id="d9"),
                entity("e1"),
                entity(" "),
            ]
        )
    )

    assert [(e.id, e.detector_id, e.origin) for e in scene.entities] == [
        ("e1", "d1", EntityOrigin.DETECTOR),
        ("e2", None, EntityOrigin.VLM),
        ("e3", None, EntityOrigin.VLM),
    ]
    assert scene.rejected == [
        "entity e2: detection d1 unknown or taken",
        "entity e3: detection d9 unknown or taken",
        "entity 'e1': empty or repeated id",
        "entity ' ': empty or repeated id",
    ]


def test_too_many_entities_actions_and_relations_are_cut():
    entities = [entity(f"e{index}") for index in range(MAX_ENTITIES + 2)]
    actions = [
        {
            "id": f"a{index}",
            "label": "يمسك",
            "actor_ids": [],
            "target_ids": ["e0"],
            "visible_evidence": ["يد"],
            "status": "observed",
        }
        for index in range(MAX_ACTIONS + 1)
    ]
    relations = [
        {"subject_id": "e0", "predicate": "فوق", "object_id": "e1", "evidence": "ظاهر"}
    ] * (MAX_RELATIONS + 1)

    scene = build(output(entities=entities, actions=actions, relations=relations))

    assert len(scene.entities) == MAX_ENTITIES
    assert len(scene.actions) == MAX_ACTIONS
    assert len(scene.relations) == MAX_RELATIONS
    assert scene.rejected == [
        f"entities beyond the first {MAX_ENTITIES} dropped",
        f"actions beyond the first {MAX_ACTIONS} dropped",
        f"relations beyond the first {MAX_RELATIONS} dropped",
    ]


# ─── Actions, relations, the rest ──────────────────────────────────


def action(identifier: str, **values: Any) -> dict[str, Any]:
    return {
        "id": identifier,
        "label": " يقرأ خبرًا ",
        "actor_ids": ["e2"],
        "target_ids": ["e1"],
        "visible_evidence": [" شاشة تعرض عنوانًا ", ""],
        "status": "inferred",
        **values,
    }


def test_actions_need_known_ids_a_visible_clue_a_label_and_a_unique_id():
    scene = build(
        output(
            entities=[entity("e1"), entity("e2", label="person")],
            actions=[
                action("a1"),
                action("a2", actor_ids=["e7"]),
                action("a3", visible_evidence=["  "]),
                action("a4", label=" "),
                action("a1"),
            ],
        )
    )

    (kept,) = scene.actions
    assert kept.label == "يقرأ خبرًا"
    assert kept.visible_evidence == ["شاشة تعرض عنوانًا"]
    assert kept.status is EvidenceStatus.INFERRED
    assert scene.rejected == [
        "action a2: unknown ids e7",
        "action a3: no visible evidence",
        "action 'a4': empty label or repeated id",
        "action 'a1': empty label or repeated id",
    ]


def test_relations_pointing_to_unknown_ids_or_without_a_predicate_are_refused():
    relation = {"subject_id": "e1", "predicate": " فوق ", "object_id": "e2", "evidence": " ظاهر "}
    scene = build(
        output(
            entities=[entity("e1"), entity("e2")],
            relations=[
                relation,
                {**relation, "object_id": "d1"},
                {**relation, "predicate": " "},
            ],
        )
    )

    assert [(r.subject_id, r.predicate, r.object_id, r.evidence) for r in scene.relations] == [
        ("e1", "فوق", "e2", "ظاهر")
    ]
    assert scene.rejected == [
        "relation ' فوق ': unknown ids d1",
        "relation e1-e2: empty predicate",
    ]


def test_an_empty_question_is_no_question_and_sensitive_categories_keep_one_order():
    scene = build(
        output(clarification_question="  ", sensitive=["violence", "alcohol", "violence"])
    )

    assert scene.clarification_question is None
    assert scene.sensitive == [SensitiveCategory.ALCOHOL, SensitiveCategory.VIOLENCE]


def test_scene_texts_lists_every_free_text():
    scene = build(
        output(
            entities=[entity("e1"), entity("e2")],
            actions=[action("a1")],
            relations=[
                {"subject_id": "e1", "predicate": "فوق", "object_id": "e2", "evidence": "ظاهر"}
            ],
        )
    )

    assert set(scene_texts(scene)) == {
        "description",
        "entities.e1.label_arabic",
        "entities.e2.label_arabic",
        "actions.a1.label",
        "actions.a1.visible_evidence.0",
        "relations.0.predicate",
        "relations.0.evidence",
        "ambiguities.0",
        "clarification_question",
    }
    assert "clarification_question" not in scene_texts(build(output(clarification_question=None)))


# ─── Box conversion ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("box", "coordinates", "expected"),
    [
        ([336, 192, 1008, 576], "pixels", (0.25, 0.25, 0.5, 0.5)),
        ([250, 250, 750, 750], "thousandths", (0.25, 0.25, 0.5, 0.5)),
        # Overshooting by less than 2 % of a side is clamped.
        ([-20, -10, 1360, 780], "pixels", (0.0, 0.0, 1.0, 1.0)),
        ([0, 0, 1015, 1010], "thousandths", (0.0, 0.0, 1.0, 1.0)),
    ],
)
def test_boxes_become_ratios(box, coordinates, expected):
    result = to_ratio_box(box, BoxCoordinates(coordinates), 1344, 768)

    assert result is not None
    assert (result.x, result.y, result.width, result.height) == pytest.approx(expected)


@pytest.mark.parametrize(
    "box",
    [
        [0, 0, 1344, 800],
        [-40, 0, 100, 100],
        [0, -20, 100, 100],
        [1400, 0, 1500, 100],
        [100, 100, 50, 200],
        [100, 100, 200, 100],
        [math.nan, 0, 10, 10],
        [0, 0, math.inf, 10],
        [-20, 0, 0, 10],
    ],
)
def test_boxes_that_are_not_in_the_image_are_refused(box):
    assert to_ratio_box(box, BoxCoordinates.PIXELS, 1344, 768) is None


def test_ratio_boxes_are_written_in_the_prompts_system():
    box = BBox(x=0.1, y=0.2, width=0.3, height=0.4)

    assert from_ratio_box(box, BoxCoordinates.PIXELS, 1000, 500) == [100, 100, 400, 300]
    assert from_ratio_box(box, BoxCoordinates.THOUSANDTHS, 1000, 500) == [100, 200, 400, 600]
