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

from src.ai.client import ModelClient, ModelImage
from src.ai.errors import AiCallError
from src.config import AiProvider
from src.pipeline.schemas import (
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


async def check_sensitivity(request: SensitivityRequest, *, client: ModelClient) -> SceneAnalysis:
    """Return the scene with the guard's verdict attached."""
    scene_categories = list(request.scene.sensitive)
    flags: list[str] = []
    error = None
    if client.provider != AiProvider.OPENAI:
        status = ModerationStatus.NOT_AVAILABLE
    else:
        try:
            moderation = await client.moderate_image(
                ModelImage(request.image.data, request.image.mime)
            )
        except AiCallError as failure:
            status, error = ModerationStatus.FAILED, failure.code
        else:
            status, flags = ModerationStatus.CHECKED, moderation.categories

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
        moderation_status=status,
        moderation_error=error,
    )
    return request.scene.model_copy(update={"guard": result})
