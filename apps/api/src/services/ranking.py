"""
The ranking of the «لك» feed: freshness, follows, variety and what the reader has already met.

Every number here is one a reader can be told, and the feed tells them (`why`): a post is
higher because it is new, because its author is followed, because it brings a topic the
list has not shown yet, or lower because the reader has already met it or the list already
has that topic. Nothing here reads anyone's religion, age, gender, health or place, nothing
is learned from clicks, and nothing is a model: it is arithmetic on four facts about a post.

The ranking is a pure function of the candidates, the moment it was made and the reader's own
signals, so a page asked for later with the same cursor continues the same list.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from src import messages
from src.schemas.social import WhyOut

# A post's freshness halves every day: new enough to matter, never forever.
HALF_LIFE_HOURS = 24.0
FOLLOW_BONUS = 0.5
# Already met (liked, saved or discussed by the reader): pushed down, not hidden.
SEEN_PENALTY = 0.8
# Each earlier post in the list on the same concept lowers a post by this much, up to the cap.
DIVERSITY_STEP = 0.15
DIVERSITY_CAP = 0.6
# Freshness at or above this is "new" in the reason.
FRESH_REASON_AT = 0.5
SCORE_DIGITS = 6


@dataclass(frozen=True)
class Candidate:
    """What the ranking knows about a post: when, by whom, and which concepts it is about."""

    post_id: int
    author_id: uuid.UUID
    author_name: str
    published_at: datetime
    concepts: tuple[str, ...]


@dataclass(frozen=True)
class Ranked:
    candidate: Candidate
    score: float
    why: WhyOut


def freshness(published_at: datetime, now: datetime) -> float:
    """Return 1 for a post published now, falling by half each `HALF_LIFE_HOURS`."""
    hours = max((now - published_at).total_seconds() / 3600.0, 0.0)
    return float(0.5 ** (hours / HALF_LIFE_HOURS))


def _why(candidate: Candidate, *, followed: bool, fresh: float, repeats: int) -> WhyOut:
    if followed:
        text = messages.WHY_FOLLOWED_AUTHOR.format(name=candidate.author_name)
        return WhyOut(code="followed_author", text=text)
    if fresh >= FRESH_REASON_AT:
        return WhyOut(code="fresh", text=messages.WHY_FRESH)
    if candidate.concepts and repeats == 0:
        return WhyOut(code="new_topic", text=messages.WHY_NEW_TOPIC)
    return WhyOut(code="community", text=messages.WHY_COMMUNITY)


def rank(
    candidates: Sequence[Candidate],
    *,
    now: datetime,
    followed: set[uuid.UUID],
    seen: set[int],
    personalise: bool,
) -> list[Ranked]:
    """
    Order the candidates, best first; ties go to the newer id.

    With `personalise` off (the reader switched personalisation off, or is a guest) follows and
    what the reader has met count for nothing: only freshness and variety remain.
    """
    scored = []
    for candidate in candidates:
        is_followed = personalise and candidate.author_id in followed
        fresh = freshness(candidate.published_at, now)
        base = fresh + (FOLLOW_BONUS if is_followed else 0.0)
        if personalise and candidate.post_id in seen:
            base -= SEEN_PENALTY
        scored.append((base, fresh, is_followed, candidate))
    scored.sort(key=lambda row: (row[0], row[3].post_id), reverse=True)

    # Variety is charged in the order of the base score, so the best post of a topic is not
    # the one that pays for the others.
    shown: Counter[str] = Counter()
    ranked = []
    for base, fresh, is_followed, candidate in scored:
        repeats = max((shown[concept] for concept in candidate.concepts), default=0)
        penalty = min(DIVERSITY_STEP * repeats, DIVERSITY_CAP)
        shown.update(candidate.concepts)
        ranked.append(
            Ranked(
                candidate=candidate,
                score=round(base - penalty, SCORE_DIGITS),
                why=_why(candidate, followed=is_followed, fresh=fresh, repeats=repeats),
            )
        )
    ranked.sort(key=lambda row: (row.score, row.candidate.post_id), reverse=True)
    return ranked


def after(ranked: Sequence[Ranked], score: float | None, post_id: int | None) -> list[Ranked]:
    """Return the entries strictly after `(score, post_id)` in the ranked order."""
    if score is None or post_id is None:
        return list(ranked)
    return [
        row
        for row in ranked
        if row.score < score or (row.score == score and row.candidate.post_id < post_id)
    ]
