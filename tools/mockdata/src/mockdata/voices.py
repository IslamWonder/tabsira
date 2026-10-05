"""
Reflections and comments of the mock posts (task 23.4), written by the provider's composer model.

One call per post: the model receives the post's insight by its own words only (title, glimpse,
small step), never a verse or a hadith, and the countries of the author and of each commenter,
and answers the author's short reflection and one short comment per slot, a reply answering
its parent. Every text then passes what a member's text passes: the cleaning of the social
schemas (control characters, length), the scripture guard with the store (`leaks` of
`src/scans/accept.py`, as the importer runs it), and the moderation guard of member text,
whose only accepted verdict is «allow». A text that fails is dropped, never repaired, and only
accepted texts are kept: nothing else the model wrote is stored.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict
from src.ai.client import ModelClient
from src.ai.records import CallRecord
from src.config import AiStage, Settings
from src.models.social import COMMENT_MAX, REFLECTION_MAX
from src.schemas.social import clean_text
from src.services.moderation_guard import GuardVerdict, Outcome

# Characters asked for; the schemas' limits stay the hard ones.
REFLECTION_CHARS = 280
COMMENT_CHARS = 160
SPONSOR_CHARS = 220
AUTHOR = "author"
SPONSOR = "sponsor"
MAX_OUTPUT_TOKENS = 6000

# The Arabic name of each country of the generator, so the model can lend a light local flavour.
COUNTRY_NAMES = {
    "MA": "المغرب",
    "DZ": "الجزائر",
    "TN": "تونس",
    "LY": "ليبيا",
    "EG": "مصر",
    "SD": "السودان",
    "MR": "موريتانيا",
    "SA": "السعودية",
    "AE": "الإمارات",
    "QA": "قطر",
    "KW": "الكويت",
    "BH": "البحرين",
    "OM": "عُمان",
    "YE": "اليمن",
    "JO": "الأردن",
    "PS": "فلسطين",
    "SY": "سوريا",
    "LB": "لبنان",
    "IQ": "العراق",
    "SO": "الصومال",
    "DJ": "جيبوتي",
    "KM": "جزر القمر",
}

SYSTEM = f"""You write the short posts and comments of members of an Arabic social app where people
share a moment they photographed and the insight («بصيرة») it gave them.

Write in Arabic. Plain Modern Standard Arabic, or a light touch of the given country's dialect
when it sounds natural; vary the voices: some warm, some brief, some curious, some practical.
Modest, kind, everyday words of ordinary people. Never preachy.

Strict rules:
- Never quote or paraphrase the Quran or a hadith, never write a verse or a saying of the
  Prophet, never use quotation marks around religious words.
- No religious rulings (no halal, haram, obligatory, forbidden), no fatwa, no judging anyone.
- No names of any real or invented person, no @mentions, no links, no hashtags, no emojis.
- No politics, no news, no countries' disputes, no brands.
- Speak about the photo's moment and the insight's idea only. Never describe the speaker's or
  anyone's gender, age, religion, health or body; avoid adjectives that mark the speaker's
  gender.
- The reflection: one to three sentences, at most {REFLECTION_CHARS} characters, first person,
  the author's own thought after seeing the insight.
- Each comment: one sentence or two, at most {COMMENT_CHARS} characters. A comment with a
  parent replies to that comment, briefly and naturally.
- When the request's role is "sponsor", the "reflection" is the note of a person who took care of
  an insight of the atlas that nobody was looking after («كفالة»): one or two sentences, at most
  {SPONSOR_CHARS} characters, humble and grateful, about the insight's idea. Never mention its
  author, never promise or ask for a reward. Answer an empty list of comments.

Answer JSON only: the reflection, and one comment for every slot, with the slot's ref."""


class CommentText(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str
    text: str


class Voices(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reflection: str
    comments: list[CommentText]


@dataclass(frozen=True)
class Slot:
    """One comment to write: its ref, the comment it answers, the commenter's country."""

    ref: str
    parent: str | None
    country: str


@dataclass(frozen=True)
class Brief:
    """What the model is told of one post: the insight's own words, never scripture."""

    post: str
    title: str
    glimpse: str
    step: str | None
    country: str
    slots: tuple[Slot, ...]
    # `sponsor` for the note of a member who looks after an orphaned atlas entry.
    role: str = AUTHOR


@dataclass
class Written:
    """The accepted texts of one post and why the others were dropped."""

    reflection: str | None = None
    comments: dict[str, str | None] = field(default_factory=dict)
    dropped: dict[str, int] = field(default_factory=dict)
    calls: list[CallRecord] = field(default_factory=list)

    def drop(self, reason: str) -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1


# Judges one text: None when it may be shown, else the reason it may not.
Check = Callable[[str, int], Awaitable[str | None]]


def text_model(settings: Settings) -> str:
    """
    Return the model that writes the members' words: the active provider's composer model.

    Plan 23 names it. OVH's smallest text model (Qwen3.5-9B) was tried on 2026-10-05 and wrote
    broken Arabic (mixed scripts, words that do not exist), so the small model is not used.
    """
    return settings.ai.compose_model


def brief_of(
    post: str, body: dict[str, Any], country: str, slots: list[Slot], role: str = AUTHOR
) -> Brief:
    """Return the brief of a post from its insight body; the evidence is left out on purpose."""
    step = body.get("small_step")
    return Brief(
        post=post,
        title=body["title"],
        glimpse=body["glimpse"],
        step=step["text"] if step else None,
        country=country,
        slots=tuple(slots),
        role=role,
    )


def user_prompt(brief: Brief) -> str:
    """The post as JSON: the insight's words, the author's country and the comment slots."""

    def country(code: str) -> str:
        return COUNTRY_NAMES.get(code, "")

    payload = {
        "role": brief.role,
        "insight": {"title": brief.title, "glimpse": brief.glimpse, "small_step": brief.step},
        "author_country": country(brief.country),
        "comments": [
            {"ref": slot.ref, "parent": slot.parent, "country": country(slot.country)}
            for slot in brief.slots
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


async def ask(client: ModelClient, brief: Brief, model: str) -> tuple[Voices, CallRecord]:
    """One call to the small text model for the whole post."""
    result = await client.chat_json(
        Voices,
        stage=AiStage.CHAT,
        system=SYSTEM,
        user=user_prompt(brief),
        model=model,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    return result.value, result.record


async def accept_texts(brief: Brief, voices: Voices, check: Check) -> Written:
    """Keep the texts that pass every check; a reply whose parent was dropped goes too."""
    written = Written()
    limit = COMMENT_MAX if brief.role == SPONSOR else REFLECTION_MAX
    reason = await check(voices.reflection, limit)
    if reason is None:
        written.reflection = voices.reflection.strip()
    else:
        written.drop(f"reflection_{reason}")
    answered = {item.ref: item.text for item in voices.comments}
    for slot in brief.slots:
        text = answered.get(slot.ref)
        if text is None:
            reason = "missing"
        elif slot.parent is not None and written.comments.get(slot.parent) is None:
            reason = "parent_dropped"
        else:
            reason = await check(text, COMMENT_MAX)
        if reason is None and text is not None:
            written.comments[slot.ref] = text.strip()
        else:
            written.comments[slot.ref] = None
            written.drop(f"comment_{reason}")
    return written


def verdict_reason(verdict: GuardVerdict) -> str | None:
    """None when the moderation allows the text, else `moderation_<outcome>`."""
    if verdict.outcome is Outcome.ALLOW:
        return None
    return f"moderation_{verdict.outcome.value}"


def cleaned(text: str, limit: int) -> str | None:
    """The text as the social schemas clean it, or None when they refuse it or nothing is left."""
    try:
        return clean_text(text, limit)
    except ValueError:
        return None
