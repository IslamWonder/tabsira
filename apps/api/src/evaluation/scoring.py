"""
Score a scene analysis against its gold scene.

The judge is mechanical on purpose: the same answer always gets the same score,
and every point lost names the words that lost it. It does not replace a human
reading the descriptions (docs/BENCHMARK.md says so); it catches what can be
caught by rule: missing things, forbidden claims, identity words, invented
objects, a wrong sensitivity verdict, boxes in the wrong coordinate system.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, computed_field

from src.evaluation.gold import GoldRules, GoldScene, first_match
from src.pipeline.scene_analyzer import scene_texts
from src.pipeline.schemas import (
    BBox,
    Detection,
    EvidenceStatus,
    SceneAnalysis,
    SensitiveCategory,
)

BOX_DROPPED_NOTE = "box outside the image"


class SceneScore(BaseModel):
    """How one analysis compares with its gold scene."""

    model_config = ConfigDict(frozen=True)

    required_total: int
    required_found: int
    missing_entities: list[str]
    expected_actions_total: int
    expected_actions_found: int
    forbidden_claims: list[str]
    identity_inferences: list[str]
    hallucinated_entities: list[str]
    sensitive_expected: bool
    sensitive_predicted: bool
    categories: list[SensitiveCategory]
    clarification_expected: bool | None
    clarification_asked: bool
    boxes_given: int
    boxes_dropped: int
    # IoU between the model's box and the detector's box, for each entity matched to a detection.
    detector_ious: list[float]
    # For each box of the model, its best IoU with any of the reference detections:
    # measured with the detector hidden from the model, it shows where its own boxes land.
    reference_ious: list[float] = []
    rejected: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def violations(self) -> int:
        """Claims a correct analysis never makes: forbidden, identity, invented objects."""
        return (
            len(self.forbidden_claims)
            + len(self.identity_inferences)
            + len(self.hallucinated_entities)
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sensitive_correct(self) -> bool:
        return self.sensitive_expected == self.sensitive_predicted


def iou(first: BBox, second: BBox) -> float:
    """Intersection over union of two ratio boxes."""
    left, top = max(first.x, second.x), max(first.y, second.y)
    right = min(first.x + first.width, second.x + second.width)
    bottom = min(first.y + first.height, second.y + second.height)
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    union = first.width * first.height + second.width * second.height - intersection
    return intersection / union if union > 0 else 0.0


def score_scene(
    scene: SceneAnalysis,
    gold: GoldScene,
    rules: GoldRules,
    reference: Sequence[Detection] = (),
) -> SceneScore:
    """Compare an analysis with what the gold scene expects."""
    labels = [text for entity in scene.entities for text in (entity.label, entity.label_arabic)]
    described = [scene.description, *labels]
    claims = [action.label for action in scene.actions]
    claims += [relation.predicate for relation in scene.relations]
    observed = [a.label for a in scene.actions if a.status is EvidenceStatus.OBSERVED]
    visible_texts = [*scene_texts(scene).values(), *(entity.label for entity in scene.entities)]

    missing = [group[0] for group in gold.required_entities if not first_match(group, described)]
    found_actions = [group for group in gold.expected_actions if first_match(group, claims)]

    forbidden = [
        f"{rule.claim}: «{word}»"
        for rule in rules.forbidden_actions
        if (word := first_match(rule.patterns, claims))
    ]
    forbidden += [
        f"not in the image: «{word}»"
        for group in gold.forbidden_actions
        if (word := first_match(group, claims))
    ]
    forbidden += [
        f"reported as observed: «{word}»"
        for group in gold.inferred_only_actions
        if (word := first_match(group, observed))
    ]
    identity = sorted(
        {
            term
            for term in rules.identity_terms
            if first_match([term], visible_texts, exact=True) is not None
        }
    )
    invented = [word for group in gold.forbidden_entities if (word := first_match(group, labels))]

    dropped = sum(1 for note in scene.rejected if note.endswith(BOX_DROPPED_NOTE))
    given = dropped + sum(1 for entity in scene.entities if entity.model_bbox is not None)
    ious = [
        round(iou(entity.model_bbox, entity.bbox), 4)
        for entity in scene.entities
        if entity.detector_id and entity.model_bbox is not None and entity.bbox is not None
    ]
    reference_ious = [
        round(max((iou(entity.model_bbox, item.bbox) for item in reference), default=0.0), 4)
        for entity in scene.entities
        if entity.model_bbox is not None and reference
    ]
    categories = scene.guard.categories if scene.guard else scene.sensitive
    return SceneScore(
        required_total=len(gold.required_entities),
        required_found=len(gold.required_entities) - len(missing),
        missing_entities=missing,
        expected_actions_total=len(gold.expected_actions),
        expected_actions_found=len(found_actions),
        forbidden_claims=forbidden,
        identity_inferences=identity,
        hallucinated_entities=invented,
        sensitive_expected=gold.sensitive,
        sensitive_predicted=scene.is_sensitive,
        categories=list(categories),
        clarification_expected=gold.expects_clarification,
        clarification_asked=scene.clarification_question is not None,
        boxes_given=given,
        boxes_dropped=dropped,
        detector_ious=ious,
        reference_ious=reference_ious,
        rejected=len(scene.rejected),
    )
