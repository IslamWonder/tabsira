"""
The automatic guard every post reflection and every comment passes first.

The text goes to OpenAI's moderation endpoint (`omni-moderation-latest`, through the one model
client of `src/ai`) and the verdict is read from the category scores: clearly fine is
published, clearly over the line is refused with its reason, anything between waits for a
person. It fails closed: a call that cannot be made (no key, a timeout, a provider error, an
answer in the wrong shape) is not an approval, it is "ask a person". Only the text is sent,
never who wrote it. The guard is a protocol so tests and the admin area swap it without a
network.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

import httpx

from src.ai.client import ModerationResult, ProviderClient
from src.ai.errors import AiCallError
from src.config import AiProvider, Settings

log = logging.getLogger("tabsira.moderation")

# The categories that are refused whatever their score once the provider flags them.
ALWAYS_REFUSED = frozenset({"sexual/minors"})


class Outcome(StrEnum):
    ALLOW = "allow"
    REVIEW = "review"
    REJECT = "reject"


@dataclass(frozen=True)
class GuardVerdict:
    """What the guard decided, and the evidence for it; never the text it judged."""

    outcome: Outcome
    # A code for the author's message: `guard_unavailable`, `guard_uncertain`, `no_user_text`
    # or the category that refused it.
    reason: str
    # The provider's flagged categories and the scores, rounded, for the moderation log.
    details: dict[str, object] = field(default_factory=dict)


class TextGuard(Protocol):
    async def check(self, text: str) -> GuardVerdict:
        """Judge one text; a failure of any kind must answer REVIEW, never ALLOW."""


def category_key(category: str) -> str:
    """Return the top-level category: `self-harm/intent` becomes `self_harm`."""
    return category.split("/", 1)[0].replace("-", "_")


def verdict_from(
    result: ModerationResult, *, allow_score: float, reject_score: float
) -> GuardVerdict:
    """
    Apply the policy to one provider answer.

    Refused: a category the provider flagged whose score reaches `reject_score`, or one that is
    refused whenever flagged. Allowed: nothing flagged and every score under `allow_score`.
    Everything else is a person's to judge.
    """
    if not result.scores:
        # No scores is an answer in the wrong shape, not a clean text.
        return GuardVerdict(Outcome.REVIEW, "guard_unavailable", {"error": "no_scores"})
    scores = {name: round(score, 3) for name, score in result.scores.items()}
    details: dict[str, object] = {"flagged": list(result.categories), "scores": scores}
    refused = [
        name
        for name in result.categories
        if name in ALWAYS_REFUSED or scores.get(name, 0.0) >= reject_score
    ]
    if refused:
        worst = max(refused, key=lambda name: scores.get(name, 0.0))
        return GuardVerdict(Outcome.REJECT, category_key(worst), details)
    if not result.flagged and max(scores.values()) < allow_score:
        return GuardVerdict(Outcome.ALLOW, "clear", details)
    return GuardVerdict(Outcome.REVIEW, "guard_uncertain", details)


class OpenAiTextGuard:
    """The guard that calls OpenAI's moderation endpoint, with a short timeout and no retry."""

    def __init__(
        self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def check(self, text: str) -> GuardVerdict:
        settings = self._settings
        try:
            async with httpx.AsyncClient(transport=self._transport) as http:
                client = ProviderClient(
                    AiProvider.OPENAI,
                    settings.ai_openai,
                    http,
                    timeout_seconds=settings.social_guard_timeout_seconds,
                    max_retries=0,
                    backoff_seconds=0.0,
                )
                result = await client.moderate_text(text)
        except AiCallError as error:
            # The code and the reason, never the text.
            log.warning("text guard unavailable: %s", error)
            return GuardVerdict(Outcome.REVIEW, "guard_unavailable", {"error": error.code.value})
        return verdict_from(
            result,
            allow_score=settings.social_guard_allow_score,
            reject_score=settings.social_guard_reject_score,
        )


NO_TEXT = GuardVerdict(Outcome.ALLOW, "no_user_text", {})
