"""
Sensitivity: the verdict on whether a scene's image may be shown back or stored.

Two sources, combined by union (v2 §6: nudity, alcohol, drugs, gambling,
violence):
- the vision model's own `sensitive` flags, from the scene analyzer, which
  cover every category;
- on OpenAI, `omni-moderation-latest` run on the image itself. It classifies
  images for sexual content, violence and self-harm only, so it can confirm
  nudity and violence but never alcohol, drugs or gambling.

OVH has no image moderation (Qwen3Guard reads text only), so there the vision
model's flags decide alone. A moderation call that fails does not hide the
scene's own flags; the failure is recorded. Enforcing the verdict (no preview,
no storage) belongs to the scan route; this stage only states it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.ai.client import ModelClient, ModelImage
from src.ai.errors import AiCallError, AiErrorCode
from src.config import AiProvider
from src.pipeline.schemas import (
    EncodedImage,
    ModerationStatus,
    SceneAnalysis,
    SensitiveCategory,
    SensitivityRequest,
    SensitivityResult,
)

# OpenAI moderation categories that apply to images, mapped to TABSIRA's categories.
MODERATION_CATEGORIES: dict[str, SensitiveCategory] = {
    "sexual": SensitiveCategory.NUDITY,
    "sexual/minors": SensitiveCategory.NUDITY,
    "violence": SensitiveCategory.VIOLENCE,
    "violence/graphic": SensitiveCategory.VIOLENCE,
    "self-harm": SensitiveCategory.VIOLENCE,
    "self-harm/intent": SensitiveCategory.VIOLENCE,
    "self-harm/instructions": SensitiveCategory.VIOLENCE,
    "illicit/violent": SensitiveCategory.VIOLENCE,
}


@dataclass(frozen=True, slots=True)
class Moderation:
    """What the provider's image moderation said, before it meets the scene's own flags."""

    status: ModerationStatus
    flags: list[str] = field(default_factory=list)
    error: AiErrorCode | None = None


async def moderate(image: EncodedImage, *, client: ModelClient) -> Moderation:
    """
    Run the provider's image moderation on the photo alone.

    It needs nothing of the scene, so the scan starts it with the scene analysis
    and the two calls overlap; a failure is recorded, never raised.
    """
    if client.provider != AiProvider.OPENAI:
        return Moderation(ModerationStatus.NOT_AVAILABLE)
    try:
        result = await client.moderate_image(ModelImage(image.data, image.mime))
    except AiCallError as failure:
        return Moderation(ModerationStatus.FAILED, error=failure.code)
    return Moderation(ModerationStatus.CHECKED, flags=list(result.categories))


def with_moderation(scene: SceneAnalysis, moderation: Moderation) -> SceneAnalysis:
    """Return the scene with the guard's verdict: its own flags and the moderation's, by union."""
    scene_categories = list(scene.sensitive)
    flags = moderation.flags
    flagged = {MODERATION_CATEGORIES[name] for name in flags if name in MODERATION_CATEGORIES}
    moderation_categories = [category for category in SensitiveCategory if category in flagged]
    union = set(scene_categories) | flagged
    categories = [category for category in SensitiveCategory if category in union]
    result = SensitivityResult(
        sensitive=bool(categories),
        categories=categories,
        scene_categories=scene_categories,
        moderation_categories=moderation_categories,
        moderation_flags=flags,
        moderation_status=moderation.status,
        moderation_error=moderation.error,
    )
    return scene.model_copy(update={"guard": result})


async def check_sensitivity(request: SensitivityRequest, *, client: ModelClient) -> SceneAnalysis:
    """Return the scene with the guard's verdict attached."""
    return with_moderation(request.scene, await moderate(request.image, client=client))
