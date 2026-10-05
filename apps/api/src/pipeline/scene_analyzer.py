"""
SceneAnalyzer: what is in the photo, what is happening, and how we know.

The vision model sees the image itself and the detector's boxes, both in one
coordinate system that the prompt states (pixels of the image it receives, or
the 0-1000 grid Qwen-VL models are trained on: `box_coordinates` of the
provider). It returns entities, actions and relations, each with an evidence
status, visible clues for every action, its doubts, at most one question, and
the sensitive categories it sees.

The server does not take the answer on trust:
- boxes are converted to 0-1 ratios here; a box outside the image is dropped;
- a detection the model matched keeps the detector's box (the reference) and
  the model's label; one detection matches one entity at most;
- an action or relation that points to an unknown id, or an action without a
  visible clue, is refused, and the refusal is recorded in `rejected`;
- a word that names a person by religion, age or gender (v2 §0.6, §6) is replaced
  by «شخص» in every text, labels included, and the replacement is recorded in
  `rejected` (`src.pipeline.person_words`);
- every text field goes through the leak guard.

The user's profile is not an input: `SceneRequest` has no field for it.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from src.ai.client import ModelClient, ModelImage
from src.config import AiProvider, AiStage, BoxCoordinates
from src.pipeline.leak_guard import LeakGuard
from src.pipeline.person_words import (
    neutralise_arabic,
    neutralise_arabic_label,
    neutralise_english_label,
)
from src.pipeline.prompt import load_prompt
from src.pipeline.schemas import (
    BBox,
    DetectorResult,
    EntityOrigin,
    EvidenceStatus,
    SceneAction,
    SceneAnalysis,
    SceneEntity,
    SceneRelation,
    SceneRequest,
    SensitiveCategory,
)

SYSTEM_PROMPT = "scene_analyzer_system.v3"
USER_PROMPT = "scene_analyzer_user.v1"
# Room for a thinking model's reasoning plus the answer; a truncated answer is a failure.
MAX_OUTPUT_TOKENS = 8192
# A box may overshoot the image by this share of a side (and is clamped); beyond, it is
# outside the image, which usually means the model used another coordinate system.
BOX_TOLERANCE = 0.02
THOUSANDTHS_SPAN = 1000
MAX_ENTITIES = 12
MAX_ACTIONS = 6
MAX_RELATIONS = 8
RATIO_DIGITS = 4
# How a replaced person descriptor is recorded in `rejected`; the evaluation's judge reads it back.
PERSON_DESCRIPTOR_NOTE = "person descriptor replaced by "

ModelStatus = Literal["observed", "inferred", "unknown"]
ActionStatus = Literal["observed", "inferred"]
SensitiveName = Literal["nudity", "alcohol", "drugs", "gambling", "violence"]


# The field descriptions travel in the JSON schema the model must follow, so they
# repeat the prompt's rules where the model writes each value.
def _says(text: str) -> Any:
    return Field(description=text)


class ModelEntity(BaseModel):
    """A thing visible in the photo."""

    id: Annotated[str, _says("e1, e2, e3 ...")]
    label: Annotated[str, _says("English, one short lowercase noun phrase: 'cat', 'person'.")]
    label_arabic: Annotated[str, _says("Arabic name of the thing, in Arabic script: «قطة».")]
    detector_id: Annotated[str | None, _says("Id of the matching detection (d1, d2 ...) or null.")]
    box: Annotated[
        list[float] | None,
        Field(
            min_length=4,
            max_length=4,
            description="[x1, y1, x2, y2] in the stated coordinate system, or null.",
        ),
    ]
    status: ModelStatus


class ModelAction(BaseModel):
    """Something visibly happening."""

    id: Annotated[str, _says("a1, a2 ...")]
    label: Annotated[str, _says("Arabic verb phrase, in Arabic script: «يمسك الهاتف».")]
    actor_ids: Annotated[list[str], _says("Entity ids doing the action.")]
    target_ids: Annotated[list[str], _says("Entity ids the action is done to.")]
    visible_evidence: Annotated[
        list[str], _says("Arabic: the concrete clues in the photo that show the action.")
    ]
    status: ActionStatus


class ModelRelation(BaseModel):
    """How two entities relate."""

    subject_id: Annotated[str, _says("An entity id.")]
    predicate: Annotated[str, _says("Arabic: «فوق»، «بجانب»، «داخل»، «ينظر إلى».")]
    object_id: Annotated[str, _says("An entity id.")]
    evidence: Annotated[str, _says("Arabic: what in the photo shows the relation.")]


class SceneModelOutput(BaseModel):
    """The scene as the photo shows it. Every human-readable text is Arabic."""

    description: Annotated[
        str, Field(min_length=1, description="Arabic, one or two sentences. People: «شخص».")
    ]
    entities: list[ModelEntity]
    actions: list[ModelAction]
    relations: list[ModelRelation]
    ambiguities: Annotated[list[str], _says("Arabic: what the photo does not let you decide.")]
    clarification_question: Annotated[
        str | None, _says("One short Arabic question, only when it changes the meaning; else null.")
    ]
    sensitive: Annotated[list[SensitiveName], _says("Categories visibly present; usually empty.")]


async def analyze_scene(
    request: SceneRequest, *, client: ModelClient, guard: LeakGuard | None = None
) -> SceneAnalysis:
    """Describe the scene with the provider's vision model and verify the answer."""
    system = load_prompt(SYSTEM_PROMPT)
    template = load_prompt(USER_PROMPT)
    coordinates = client.settings.box_coordinates
    width, height = request.image.width, request.image.height
    user = template.render(
        width=width,
        height=height,
        coordinates=coordinate_rule(coordinates, width, height),
        detector=detector_section(request.detector, coordinates, width, height),
    )
    result = await client.chat_json(
        SceneModelOutput,
        stage=AiStage.VISION,
        system=system.text,
        user=user,
        images=[ModelImage(request.image.data, request.image.mime)],
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    analysis = build_scene(
        result.value,
        request,
        coordinates,
        provider=client.provider,
        model=result.record.model,
        prompt_version=f"{system.version}+{template.version}",
    )
    (guard or LeakGuard()).ensure_clean(scene_texts(analysis))
    return analysis


def coordinate_rule(coordinates: BoxCoordinates, width: int, height: int) -> str:
    """State the coordinate system in the words the prompt uses."""
    if coordinates is BoxCoordinates.THOUSANDTHS:
        return (
            "a 0-1000 grid on each axis, whatever the pixel size: x from 0 (left edge) to 1000 "
            "(right edge), y from 0 (top edge) to 1000 (bottom edge)."
        )
    return (
        f"pixels of this photo: x from 0 (left edge) to {width} (right edge), "
        f"y from 0 (top edge) to {height} (bottom edge)."
    )


def detector_section(
    detector: DetectorResult, coordinates: BoxCoordinates, width: int, height: int
) -> str:
    """Describe the detector's boxes in the prompt's coordinate system."""
    if not detector.available:
        return "not available for this photo; rely on the image alone."
    if not detector.detections:
        return "it found nothing; rely on the image alone."
    lines = [
        json.dumps(
            {
                "id": item.id,
                "label": item.label,
                "label_arabic": item.label_arabic,
                "confidence": round(item.confidence, 2),
                "box": from_ratio_box(item.bbox, coordinates, width, height),
            },
            ensure_ascii=False,
        )
        for item in detector.detections
    ]
    return "these detections, one per line, may be wrong:\n" + "\n".join(lines)


def _spans(coordinates: BoxCoordinates, width: int, height: int) -> tuple[int, int]:
    if coordinates is BoxCoordinates.THOUSANDTHS:
        return THOUSANDTHS_SPAN, THOUSANDTHS_SPAN
    return width, height


def from_ratio_box(box: BBox, coordinates: BoxCoordinates, width: int, height: int) -> list[int]:
    """Return `[x1, y1, x2, y2]` of a ratio box in the given coordinate system."""
    span_x, span_y = _spans(coordinates, width, height)
    return [
        round(box.x * span_x),
        round(box.y * span_y),
        round((box.x + box.width) * span_x),
        round((box.y + box.height) * span_y),
    ]


def to_ratio_box(
    box: Sequence[float], coordinates: BoxCoordinates, width: int, height: int
) -> BBox | None:
    """Convert a model's `[x1, y1, x2, y2]` to ratios; None when it is not a box in the image."""
    span_x, span_y = _spans(coordinates, width, height)
    x1, y1, x2, y2 = box
    if not all(math.isfinite(value) for value in box) or x2 <= x1 or y2 <= y1:
        return None
    slack_x, slack_y = BOX_TOLERANCE * span_x, BOX_TOLERANCE * span_y
    if x1 < -slack_x or y1 < -slack_y or x2 > span_x + slack_x or y2 > span_y + slack_y:
        return None
    left, top = max(x1, 0.0) / span_x, max(y1, 0.0) / span_y
    right, bottom = min(x2, span_x) / span_x, min(y2, span_y) / span_y
    if right <= left or bottom <= top:
        return None
    return BBox(
        x=round(left, RATIO_DIGITS),
        y=round(top, RATIO_DIGITS),
        width=round(right - left, RATIO_DIGITS),
        height=round(bottom - top, RATIO_DIGITS),
    )


def build_scene(
    output: SceneModelOutput,
    request: SceneRequest,
    coordinates: BoxCoordinates,
    *,
    provider: AiProvider,
    model: str,
    prompt_version: str,
) -> SceneAnalysis:
    """Turn the model's answer into a verified scene, recording every refusal."""
    rejected: list[str] = []
    entities, claimed = _entities(output, request, coordinates, rejected)
    known = {entity.id for entity in entities}
    actions = _actions(output, known, rejected)
    relations = _relations(output, known, rejected)
    question = (output.clarification_question or "").strip() or None
    return SceneAnalysis(
        description=_neutral(output.description.strip(), "description", rejected),
        entities=entities,
        actions=actions,
        relations=relations,
        ambiguities=[
            _neutral(text.strip(), f"ambiguities.{index}", rejected)
            for index, text in enumerate(text for text in output.ambiguities if text.strip())
        ],
        clarification_question=_neutral(question, "clarification_question", rejected)
        if question
        else None,
        sensitive=[category for category in SensitiveCategory if category in output.sensitive],
        detector_available=request.detector.available,
        unconfirmed_detection_ids=[
            item.id for item in request.detector.detections if item.id not in claimed
        ],
        rejected=rejected,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
    )


def _neutral(text: str, where: str, rejected: list[str], *, label: bool = False) -> str:
    """Return `text` with its person descriptors replaced, recording each replacement."""
    result = neutralise_arabic_label(text) if label else neutralise_arabic(text)
    if result.changed:
        words = ", ".join(result.replaced)
        rejected.append(f"{where}: {PERSON_DESCRIPTOR_NOTE}«شخص»: {words}")
    return result.text


def _neutral_label(label: str, where: str, rejected: list[str]) -> str:
    """Return the English label, or "person" when it names one by a descriptor."""
    result = neutralise_english_label(label)
    if result.changed:
        rejected.append(f"{where}: {PERSON_DESCRIPTOR_NOTE}'person': {', '.join(result.replaced)}")
    return result.text


def _entities(
    output: SceneModelOutput,
    request: SceneRequest,
    coordinates: BoxCoordinates,
    rejected: list[str],
) -> tuple[list[SceneEntity], set[str]]:
    detections = {item.id: item for item in request.detector.detections}
    width, height = request.image.width, request.image.height
    entities: list[SceneEntity] = []
    claimed: set[str] = set()
    if len(output.entities) > MAX_ENTITIES:
        rejected.append(f"entities beyond the first {MAX_ENTITIES} dropped")
    for item in output.entities[:MAX_ENTITIES]:
        entity_id = item.id.strip()
        if not entity_id or entity_id in {entity.id for entity in entities}:
            rejected.append(f"entity {item.id!r}: empty or repeated id")
            continue
        model_bbox = None
        if item.box is not None:
            model_bbox = to_ratio_box(item.box, coordinates, width, height)
            if model_bbox is None:
                rejected.append(f"entity {entity_id}: box outside the image")
        detection = detections.get(item.detector_id) if item.detector_id else None
        if item.detector_id and (detection is None or detection.id in claimed):
            rejected.append(f"entity {entity_id}: detection {item.detector_id} unknown or taken")
            detection = None
        if detection is not None:
            claimed.add(detection.id)
        entities.append(
            SceneEntity(
                id=entity_id,
                label=_neutral_label(
                    item.label.strip().lower(), f"entity {entity_id} label", rejected
                ),
                label_arabic=_neutral(
                    item.label_arabic.strip(),
                    f"entity {entity_id} label_arabic",
                    rejected,
                    label=True,
                ),
                bbox=detection.bbox if detection else model_bbox,
                origin=EntityOrigin.DETECTOR if detection else EntityOrigin.VLM,
                status=EvidenceStatus(item.status),
                detector_id=detection.id if detection else None,
                model_bbox=model_bbox,
            )
        )
    return entities, claimed


def _actions(output: SceneModelOutput, known: set[str], rejected: list[str]) -> list[SceneAction]:
    actions: list[SceneAction] = []
    if len(output.actions) > MAX_ACTIONS:
        rejected.append(f"actions beyond the first {MAX_ACTIONS} dropped")
    for item in output.actions[:MAX_ACTIONS]:
        unknown = sorted({*item.actor_ids, *item.target_ids} - known)
        evidence = [text.strip() for text in item.visible_evidence if text.strip()]
        if unknown:
            rejected.append(f"action {item.id}: unknown ids {', '.join(unknown)}")
        elif not evidence:
            rejected.append(f"action {item.id}: no visible evidence")
        elif not item.label.strip() or item.id in {action.id for action in actions}:
            rejected.append(f"action {item.id!r}: empty label or repeated id")
        else:
            actions.append(
                SceneAction(
                    id=item.id,
                    label=_neutral(item.label.strip(), f"action {item.id} label", rejected),
                    actor_ids=item.actor_ids,
                    target_ids=item.target_ids,
                    visible_evidence=[
                        _neutral(text, f"action {item.id} evidence", rejected) for text in evidence
                    ],
                    status=EvidenceStatus(item.status),
                )
            )
    return actions


def _relations(
    output: SceneModelOutput, known: set[str], rejected: list[str]
) -> list[SceneRelation]:
    relations: list[SceneRelation] = []
    if len(output.relations) > MAX_RELATIONS:
        rejected.append(f"relations beyond the first {MAX_RELATIONS} dropped")
    for item in output.relations[:MAX_RELATIONS]:
        unknown = sorted({item.subject_id, item.object_id} - known)
        if unknown:
            rejected.append(f"relation {item.predicate!r}: unknown ids {', '.join(unknown)}")
        elif not item.predicate.strip():
            rejected.append(f"relation {item.subject_id}-{item.object_id}: empty predicate")
        else:
            where = f"relation {item.subject_id}-{item.object_id}"
            relations.append(
                SceneRelation(
                    subject_id=item.subject_id,
                    predicate=_neutral(item.predicate.strip(), f"{where} predicate", rejected),
                    object_id=item.object_id,
                    evidence=_neutral(item.evidence.strip(), f"{where} evidence", rejected),
                )
            )
    return relations


def scene_texts(scene: SceneAnalysis) -> dict[str, str]:
    """Every free text of a scene, keyed by where it is, for the leak guard."""
    texts = {"description": scene.description}
    texts |= {f"entities.{e.id}.label_arabic": e.label_arabic for e in scene.entities}
    for action in scene.actions:
        texts[f"actions.{action.id}.label"] = action.label
        texts |= {
            f"actions.{action.id}.visible_evidence.{index}": text
            for index, text in enumerate(action.visible_evidence)
        }
    for index, relation in enumerate(scene.relations):
        texts[f"relations.{index}.predicate"] = relation.predicate
        texts[f"relations.{index}.evidence"] = relation.evidence
    texts |= {f"ambiguities.{index}": text for index, text in enumerate(scene.ambiguities)}
    if scene.clarification_question:
        texts["clarification_question"] = scene.clarification_question
    return texts
