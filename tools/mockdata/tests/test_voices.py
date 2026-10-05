from __future__ import annotations

import json

from src.config import AiStage
from src.services.moderation_guard import GuardVerdict, Outcome

from mockdata.scan import body_of
from mockdata.voices import (
    SYSTEM,
    Brief,
    Slot,
    Voices,
    accept_texts,
    ask,
    brief_of,
    cleaned,
    text_model,
    user_prompt,
    verdict_reason,
)

from .fakes import FakeClient, insight, settings

BRIEF = Brief(
    post="p1",
    title="سكينة القطة",
    glimpse="هدوء",
    step="أطعم قطة",
    country="TN",
    slots=(Slot("c1", None, "EG"), Slot("c2", "c1", "MA"), Slot("c3", None, "XX")),
)


def test_the_members_words_come_from_the_composer_model() -> None:
    assert text_model(settings(ai_provider="ovh")) == "Qwen3.8-27B"
    assert text_model(settings(ai_provider="openai")) == "gpt-5.4-mini-2026-03-17"


def test_the_brief_carries_the_insights_words_and_no_evidence() -> None:
    brief = brief_of("p1", body_of(insight()), "TN", [Slot("c1", None, "EG")])
    assert (brief.title, brief.glimpse, brief.step) == (
        "سكينة القطة",
        "هدوء يدعو إلى التأمل",
        "أطعم قطة اليوم",
    )
    assert brief.slots == (Slot("c1", None, "EG"),)
    assert brief_of("p1", body_of(insight(step=False)), "TN", []).step is None


def test_the_prompt_names_countries_in_arabic_and_holds_no_reference() -> None:
    payload = json.loads(user_prompt(BRIEF))
    assert payload["author_country"] == "تونس"
    assert payload["comments"] == [
        {"ref": "c1", "parent": None, "country": "مصر"},
        {"ref": "c2", "parent": "c1", "country": "المغرب"},
        {"ref": "c3", "parent": None, "country": ""},
    ]
    assert set(payload["insight"]) == {"title", "glimpse", "small_step"}
    assert "Quran" in SYSTEM


async def test_one_call_per_post_to_the_given_model() -> None:
    answer = {"reflection": "تأملت", "comments": [{"ref": "c1", "text": "جميل"}]}
    client = FakeClient([answer])
    voices, record = await ask(client, BRIEF, "the-model")
    assert voices.reflection == "تأملت"
    assert record.model == "the-model"
    assert client.calls[0]["stage"] is AiStage.CHAT
    assert client.calls[0]["model"] == "the-model"


async def _allow_all(text: str, limit: int) -> str | None:
    return None


async def test_every_text_that_passes_is_kept_trimmed() -> None:
    voices = Voices(
        reflection=" تأملت ",
        comments=[
            {"ref": "c1", "text": "جميل"},
            {"ref": "c2", "text": "صحيح "},
            {"ref": "c3", "text": "شكرا"},
        ],
    )
    written = await accept_texts(BRIEF, voices, _allow_all)
    assert written.reflection == "تأملت"
    assert written.comments == {"c1": "جميل", "c2": "صحيح", "c3": "شكرا"}
    assert written.dropped == {}


async def test_a_refused_text_is_dropped_and_its_replies_with_it() -> None:
    async def check(text: str, limit: int) -> str | None:
        return "scripture" if text in {"آية", "تعليق"} else None

    voices = Voices.model_validate(
        {
            "reflection": "آية",
            "comments": [{"ref": "c1", "text": "تعليق"}, {"ref": "c2", "text": "رد"}],
        }
    )
    written = await accept_texts(BRIEF, voices, check)
    assert written.reflection is None
    assert written.comments == {"c1": None, "c2": None, "c3": None}
    assert written.dropped == {
        "reflection_scripture": 1,
        "comment_scripture": 1,
        "comment_parent_dropped": 1,
        "comment_missing": 1,
    }


async def test_the_limits_are_the_schemas() -> None:
    limits: list[int] = []

    async def check(text: str, limit: int) -> str | None:
        limits.append(limit)
        return None

    voices = Voices.model_validate({"reflection": "ر", "comments": [{"ref": "c1", "text": "ت"}]})
    await accept_texts(BRIEF, voices, check)
    assert limits == [800, 500]


def test_only_allow_passes_the_moderation() -> None:
    assert verdict_reason(GuardVerdict(Outcome.ALLOW, "clear")) is None
    assert verdict_reason(GuardVerdict(Outcome.REVIEW, "guard_uncertain")) == "moderation_review"
    assert verdict_reason(GuardVerdict(Outcome.REJECT, "violence")) == "moderation_reject"


def test_cleaned_is_the_social_schemas_cleaning() -> None:
    assert cleaned(" نص ", 10) == "نص"
    assert cleaned("   ", 10) is None
    assert cleaned("نص\u202e", 10) is None
    assert cleaned("طويل جدا", 3) is None
