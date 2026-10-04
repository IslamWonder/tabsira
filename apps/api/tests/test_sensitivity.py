from __future__ import annotations

import pytest

from src.ai.errors import AiCallError, AiErrorCode
from src.config import AiProvider
from src.pipeline.schemas import (
    EncodedImage,
    ModerationStatus,
    SceneAnalysis,
    SensitiveCategory,
    SensitivityRequest,
)
from src.pipeline.sensitivity import check_sensitivity
from tests.fakes import FakeModelClient

IMAGE = EncodedImage(data=b"stripped-jpeg", width=1344, height=768)


def scene(*sensitive: SensitiveCategory) -> SceneAnalysis:
    return SceneAnalysis(
        description="كأسان على طاولة",
        entities=[],
        actions=[],
        relations=[],
        ambiguities=[],
        clarification_question=None,
        sensitive=list(sensitive),
        detector_available=True,
        unconfirmed_detection_ids=[],
        rejected=[],
        provider=AiProvider.OPENAI,
        model="m",
        prompt_version="v",
    )


async def test_on_ovh_the_vision_models_flags_decide_alone():
    client = FakeModelClient(AiProvider.OVH)
    request = SensitivityRequest(image=IMAGE, scene=scene(SensitiveCategory.ALCOHOL))

    guarded = await check_sensitivity(request, client=client)

    assert client.moderated == []
    guard = guarded.guard
    assert guard is not None
    assert guard.moderation_status is ModerationStatus.NOT_AVAILABLE
    assert guard.categories == [SensitiveCategory.ALCOHOL]
    assert guard.scene_categories == [SensitiveCategory.ALCOHOL]
    assert guard.moderation_categories == []
    assert guard.sensitive
    assert guarded.is_sensitive
    assert guarded.model_dump()["is_sensitive"] is True


async def test_on_openai_the_image_moderation_adds_what_it_saw():
    client = FakeModelClient(
        AiProvider.OPENAI, moderations=[(True, ["harassment", "violence", "violence/graphic"])]
    )
    request = SensitivityRequest(image=IMAGE, scene=scene(SensitiveCategory.ALCOHOL))

    guarded = await check_sensitivity(request, client=client)

    assert client.moderated[0].data == b"stripped-jpeg"
    guard = guarded.guard
    assert guard is not None
    assert guard.moderation_status is ModerationStatus.CHECKED
    assert guard.moderation_flags == ["harassment", "violence", "violence/graphic"]
    assert guard.moderation_categories == [SensitiveCategory.VIOLENCE]
    assert guard.categories == [SensitiveCategory.ALCOHOL, SensitiveCategory.VIOLENCE]
    assert guard.moderation_error is None


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        (["sexual"], [SensitiveCategory.NUDITY]),
        (["sexual/minors"], [SensitiveCategory.NUDITY]),
        (["self-harm/intent"], [SensitiveCategory.VIOLENCE]),
        (["illicit/violent"], [SensitiveCategory.VIOLENCE]),
        (["hate"], []),
        ([], []),
    ],
)
async def test_moderation_categories_map_to_ours(flags, expected):
    client = FakeModelClient(AiProvider.OPENAI, moderations=[(bool(flags), flags)])

    guarded = await check_sensitivity(SensitivityRequest(image=IMAGE, scene=scene()), client=client)

    assert guarded.guard is not None
    assert guarded.guard.categories == expected
    assert guarded.is_sensitive is bool(expected)


async def test_a_failed_moderation_keeps_the_scene_flags_and_says_it_failed():
    client = FakeModelClient(
        AiProvider.OPENAI, moderations=[AiCallError(AiErrorCode.TIMEOUT, "slow")]
    )
    request = SensitivityRequest(image=IMAGE, scene=scene(SensitiveCategory.GAMBLING))

    guarded = await check_sensitivity(request, client=client)

    guard = guarded.guard
    assert guard is not None
    assert guard.moderation_status is ModerationStatus.FAILED
    assert guard.moderation_error is AiErrorCode.TIMEOUT
    assert guard.categories == [SensitiveCategory.GAMBLING]


def test_a_scene_without_a_guard_is_sensitive_from_its_own_flags():
    assert scene(SensitiveCategory.DRUGS).is_sensitive
    assert not scene().is_sensitive
