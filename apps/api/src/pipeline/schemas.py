"""
The schemas the scan pipeline's stages take and return.

Each stage is a function from one of these models to another (v2 §6). Boxes
are always ratios (0 to 1) of the image, `x` and `y` being the top-left corner;
pixel and 0-1000 boxes exist only inside the stage that converts them.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, computed_field

from src.ai.errors import AiErrorCode
from src.config import AiProvider

Ratio = Annotated[float, Field(ge=0, le=1)]


class FrozenModel(BaseModel):
    """A stage value: immutable, and bytes travel as base64 if it is ever serialised."""

    model_config = ConfigDict(frozen=True, ser_json_bytes="base64", val_json_bytes="base64")


# ─── Image ─────────────────────────────────────────────────────────


class ImageFormat(StrEnum):
    """The formats a photo may arrive in."""

    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"


class ImageUpload(FrozenModel):
    """The bytes of a photo as received, before any check."""

    data: bytes


class EncodedImage(FrozenModel):
    """A JPEG with every metadata block removed: what may leave the server."""

    data: bytes
    mime: str = "image/jpeg"
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]


class CaptureLocation(FrozenModel):
    """Where the camera says the photo was taken. Zero is a value, not a missing one."""

    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]
    altitude_m: float | None = None


class CaptureMetadata(FrozenModel):
    """
    Private facts about the capture, kept apart from the image.

    It never reaches a model and never a public API; the atlas may offer it to
    the owner as a starting point, and approximates it on the server.
    """

    location: CaptureLocation | None = None


class ValidatedImage(FrozenModel):
    """A photo that passed the checks, upright, re-encoded without metadata."""

    source_format: ImageFormat
    source_bytes: int
    # Full size, for the owner's consented storage.
    image: EncodedImage
    # The copy every model and the detector receive (see image_validator.model_size).
    model_image: EncodedImage
    capture: CaptureMetadata


# ─── Detector ──────────────────────────────────────────────────────


class BBox(FrozenModel):
    """A box as ratios of the image; `x` and `y` are its top-left corner."""

    x: Ratio
    y: Ratio
    width: Ratio
    height: Ratio


class Detection(FrozenModel):
    """One object the detector found."""

    id: str
    label: str
    # None when the detector's vocabulary has no Arabic name for the label: never guessed.
    label_arabic: str | None
    confidence: Ratio
    bbox: BBox


class DetectorRequest(FrozenModel):
    """What to look for in which image; None leaves the detector's own default."""

    image: EncodedImage
    vocabulary: list[str] | None = None
    confidence: Ratio | None = None
    max_detections: Annotated[int, Field(ge=1, le=300)] | None = None


class DetectorResult(FrozenModel):
    """The detector's boxes, or the reason it was skipped."""

    available: bool
    detections: list[Detection] = Field(default_factory=list)
    model: str | None = None
    # Time inside the detector (inference), and wall time of the whole request.
    detector_ms: int | None = None
    latency_ms: int
    # Set when the detector was skipped: timeout, unreachable, http_503, invalid_response.
    error: str | None = None


# ─── Scene ─────────────────────────────────────────────────────────


class EvidenceStatus(StrEnum):
    """How an understanding is known (v2 §0, rule 3)."""

    OBSERVED = "observed"
    INFERRED = "inferred"
    USER_CONFIRMED = "user_confirmed"
    UNKNOWN = "unknown"


class EntityOrigin(StrEnum):
    """Where an entity's box comes from."""

    DETECTOR = "detector"
    VLM = "vlm"
    USER_SELECTION = "user_selection"


class SensitiveCategory(StrEnum):
    """Scenes whose image is never shown back nor stored (v2 §6)."""

    NUDITY = "nudity"
    ALCOHOL = "alcohol"
    DRUGS = "drugs"
    GAMBLING = "gambling"
    VIOLENCE = "violence"


class SceneRequest(FrozenModel):
    """
    What the scene analyzer receives: the model copy of the photo and the detector's boxes.

    Nothing about the user is here, by design: the religion and gender profile
    is added after this stage, when meanings are chosen (v2 §6).
    """

    image: EncodedImage
    detector: DetectorResult


class SceneEntity(FrozenModel):
    """A thing in the scene."""

    id: str
    label: str
    label_arabic: str
    # The box the scene keeps: the detector's when the model matched one, else the model's.
    bbox: BBox | None
    origin: EntityOrigin
    status: EvidenceStatus
    detector_id: str | None = None
    # The model's own box, converted, kept even when the detector's wins (for measuring).
    model_bbox: BBox | None = None


class SceneAction(FrozenModel):
    """Something happening, with the visible clues that show it."""

    id: str
    label: str
    actor_ids: list[str]
    target_ids: list[str]
    visible_evidence: Annotated[list[str], Field(min_length=1)]
    status: EvidenceStatus


class SceneRelation(FrozenModel):
    """How two entities relate, and what in the image shows it."""

    subject_id: str
    predicate: str
    object_id: str
    evidence: str


class ModerationStatus(StrEnum):
    """Whether the provider's own image moderation looked at the photo."""

    CHECKED = "checked"
    # The provider has no image moderation (OVH): the vision model's flags decide alone.
    NOT_AVAILABLE = "not_available"
    FAILED = "failed"


class SensitivityResult(FrozenModel):
    """The guard's verdict: the union of what the vision model and the moderation saw."""

    sensitive: bool
    categories: list[SensitiveCategory]
    scene_categories: list[SensitiveCategory]
    moderation_categories: list[SensitiveCategory]
    # The provider's own flagged category names, kept as given (sexual, violence/graphic ...).
    moderation_flags: list[str]
    moderation_status: ModerationStatus
    moderation_error: AiErrorCode | None = None


class SceneAnalysis(FrozenModel):
    """The verified structure of a scene (v2 §6)."""

    description: str
    entities: list[SceneEntity]
    actions: list[SceneAction]
    relations: list[SceneRelation]
    ambiguities: list[str]
    clarification_question: str | None
    # Categories the vision model saw; the guard's verdict is added by the sensitivity stage.
    sensitive: list[SensitiveCategory]
    detector_available: bool
    # Detections no entity confirmed: the detector may be wrong, so they are not entities.
    unconfirmed_detection_ids: list[str]
    # What the server refused in the model's answer, and why.
    rejected: list[str]
    provider: AiProvider
    model: str
    prompt_version: str
    # Set by the sensitivity stage. A sensitive scene's image is never shown back nor stored.
    guard: SensitivityResult | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_sensitive(self) -> bool:
        """True when the vision model or the guard found a sensitive category."""
        return bool(self.sensitive) or (self.guard is not None and self.guard.sensitive)


class SensitivityRequest(FrozenModel):
    """The photo the moderation may look at, and the scene whose flags it completes."""

    image: EncodedImage
    scene: SceneAnalysis
