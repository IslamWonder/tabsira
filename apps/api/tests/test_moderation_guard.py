"""The automatic guard: the policy over the provider's scores, and failing closed."""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from src.ai.client import ModerationResult
from src.deps import get_text_guard
from src.services.moderation_guard import (
    NO_TEXT,
    GuardVerdict,
    OpenAiTextGuard,
    Outcome,
    category_key,
    verdict_from,
)
from tests.fakes import make_record


def result(flagged: bool, categories: list[str], scores: dict[str, float]) -> ModerationResult:
    return ModerationResult(
        flagged=flagged, categories=categories, scores=scores, record=make_record()
    )


def judge(answer: ModerationResult) -> GuardVerdict:
    return verdict_from(answer, allow_score=0.4, reject_score=0.85)


@pytest.mark.parametrize(
    ("category", "key"),
    [
        ("harassment", "harassment"),
        ("harassment/threatening", "harassment"),
        ("self-harm/intent", "self_harm"),
        ("sexual/minors", "sexual"),
        ("illicit/violent", "illicit"),
    ],
)
def test_a_category_is_reduced_to_its_top_level_key(category, key):
    assert category_key(category) == key


def test_a_text_with_nothing_flagged_and_low_scores_is_allowed():
    verdict = judge(result(False, [], {"hate": 0.01, "violence": 0.2}))

    assert (verdict.outcome, verdict.reason) == (Outcome.ALLOW, "clear")
    assert verdict.details == {"flagged": [], "scores": {"hate": 0.01, "violence": 0.2}}


def test_a_text_with_no_scores_at_all_is_allowed_only_when_nothing_is_flagged():
    assert judge(result(False, [], {})).outcome is Outcome.ALLOW
    assert judge(result(True, ["hate"], {})).outcome is Outcome.REVIEW


def test_a_flagged_text_under_the_reject_score_waits_for_a_person():
    verdict = judge(result(True, ["harassment"], {"harassment": 0.6}))

    assert (verdict.outcome, verdict.reason) == (Outcome.REVIEW, "guard_uncertain")
    assert verdict.details["flagged"] == ["harassment"]


def test_an_unflagged_text_with_a_middling_score_waits_for_a_person():
    assert judge(result(False, [], {"violence": 0.5})).outcome is Outcome.REVIEW


def test_a_text_over_the_reject_score_is_refused_with_its_worst_category():
    verdict = judge(
        result(
            True,
            ["harassment", "hate/threatening"],
            {"harassment": 0.9, "hate/threatening": 0.97, "violence": 0.1},
        )
    )

    assert (verdict.outcome, verdict.reason) == (Outcome.REJECT, "hate")


def test_a_category_that_is_refused_whenever_flagged_is_refused_at_any_score():
    verdict = judge(result(True, ["sexual/minors"], {"sexual/minors": 0.2}))

    assert (verdict.outcome, verdict.reason) == (Outcome.REJECT, "sexual")


def test_a_score_over_the_reject_line_for_a_category_the_provider_did_not_flag_is_not_a_refusal():
    # Only what the provider flagged can be refused; a stray score waits for a person.
    verdict = judge(result(False, [], {"violence": 0.95}))

    assert verdict.outcome is Outcome.REVIEW


def test_a_post_with_no_words_of_its_author_has_nothing_to_judge():
    assert (NO_TEXT.outcome, NO_TEXT.reason) == (Outcome.ALLOW, "no_user_text")


# ─── The OpenAI guard, against a mock transport ───────────────────────────────


@pytest.fixture
def keyed(make_settings):
    return make_settings(ai_openai={"api_key": "sk-test-key"})


def guard_with(settings, handler):
    return OpenAiTextGuard(settings, transport=httpx.MockTransport(handler))


def moderation_answer(flagged, categories, scores):
    return httpx.Response(
        200,
        json={
            "id": "modr-1",
            "results": [
                {
                    "flagged": flagged,
                    "categories": categories,
                    "category_scores": scores,
                }
            ],
        },
    )


async def test_the_guard_sends_only_the_text_to_the_moderation_model_and_reads_the_scores(keyed):
    seen = []

    def handler(request):
        seen.append((str(request.url), json.loads(request.content), request.headers))
        return moderation_answer(False, {"hate": False}, {"hate": 0.001})

    verdict = await guard_with(keyed, handler).check("نص التأمل")

    assert verdict.outcome is Outcome.ALLOW
    url, body, headers = seen[0]
    assert url == "https://api.openai.com/v1/moderations"
    assert body == {"model": "omni-moderation-latest", "input": "نص التأمل"}
    assert headers["authorization"] == "Bearer sk-test-key"


async def test_the_guard_refuses_what_the_provider_flags_over_the_line(keyed):
    def handler(request):
        return moderation_answer(True, {"harassment": True}, {"harassment": 0.93})

    verdict = await guard_with(keyed, handler).check("x")

    assert (verdict.outcome, verdict.reason) == (Outcome.REJECT, "harassment")


async def test_the_scores_in_the_policy_follow_the_settings(make_settings):
    strict = make_settings(
        ai_openai={"api_key": "k"}, social_guard_allow_score=0.05, social_guard_reject_score=0.5
    )

    def handler(request):
        return moderation_answer(True, {"violence": True}, {"violence": 0.6})

    assert (await guard_with(strict, handler).check("x")).outcome is Outcome.REJECT


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={"error": {"message": "boom"}}),
        httpx.Response(401, json={"error": {"message": "bad key"}}),
        httpx.Response(200, json={"results": []}),
        httpx.Response(200, text="not json"),
    ],
)
async def test_a_failed_call_holds_the_text_for_a_person_and_never_allows_it(keyed, response):
    verdict = await guard_with(keyed, lambda request: response).check("نص")

    assert verdict.outcome is Outcome.REVIEW
    assert verdict.reason == "guard_unavailable"
    assert "error" in verdict.details


async def test_a_timeout_or_a_network_error_holds_the_text(keyed):
    def timeout(request):
        raise httpx.ReadTimeout("slow")

    def down(request):
        raise httpx.ConnectError("no route")

    assert (await guard_with(keyed, timeout).check("x")).reason == "guard_unavailable"
    assert (await guard_with(keyed, down).check("x")).reason == "guard_unavailable"


async def test_without_a_key_the_guard_makes_no_call_and_holds_the_text(make_settings):
    calls = []

    def handler(request):
        calls.append(request)
        return moderation_answer(False, {}, {})

    verdict = await guard_with(make_settings(), handler).check("x")

    assert verdict.reason == "guard_unavailable"
    assert verdict.details == {"error": "not_configured"}
    assert calls == []


async def test_the_failure_is_logged_without_the_text(keyed, caplog):
    secret = "كلمة سرية في التأمل"

    with caplog.at_level(logging.WARNING, logger="tabsira.moderation"):
        await guard_with(keyed, lambda request: httpx.Response(500, json={})).check(secret)

    assert "text guard unavailable" in caplog.text
    assert secret not in caplog.text


def test_the_dependency_is_the_openai_guard_unless_the_application_holds_another(account_app):
    from types import SimpleNamespace

    request = SimpleNamespace(app=account_app)

    default = get_text_guard(request, account_app.state.settings)
    account_app.state.text_guard = NO_TEXT
    custom = get_text_guard(request, account_app.state.settings)

    assert isinstance(default, OpenAiTextGuard)
    assert custom is NO_TEXT
