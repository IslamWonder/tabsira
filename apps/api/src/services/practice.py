"""
Practice, never piety (decision 27): ranks, streak, the daily quest, the sky of meanings, badges.

Every rule here is a pure function of recorded events (a finished look, a
completed insight, a declared step, a place, a treasure, a question) and of the
learner's day. No model awards anything, nothing compares people, nothing is
lost by missing a day except the current run of the streak, and nothing claims
faith, reward or acceptance; every surface shows the practice disclaimer
(decision 27).

- A look is a scan of the learner's own photo that ended with insights.
- Ranks: ناظر from 0 looks, متأمّل from 3, مستبصر from 10, بصير بالتمرين from 30.
- Streak: consecutive days with a look; today may still come, so a run that
  ended yesterday is current. A missed day resets the current run, never the best.
- The daily quest «بصيرة اليوم»: a look and a completed insight on the same day.
- The sky: one star per concept of a completed insight, its place fixed by its name.
- A badge records when its rule first held; it is never taken back.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.messages import messages_for

RANK_THRESHOLDS = (0, 3, 10, 30)
UTC_ZONE = ZoneInfo("UTC")
TUTORIAL_SLUGS = ("drop", "planting")
RECENT_DAYS = 7
SKY_MARGIN = 0.05


@dataclass(frozen=True)
class PracticeLog:
    """The learner's recorded events, each list sorted by time."""

    looks: list[datetime] = field(default_factory=list)
    # (time, concept) of every completed insight.
    completions: list[tuple[datetime, str]] = field(default_factory=list)
    # slug -> time a prepared tutorial insight was completed.
    tutorial: dict[str, datetime] = field(default_factory=dict)
    actions: list[datetime] = field(default_factory=list)
    places: list[datetime] = field(default_factory=list)
    treasures: list[datetime] = field(default_factory=list)
    questions: list[datetime] = field(default_factory=list)


@dataclass(frozen=True)
class Rank:
    id: str
    title: str
    hint: str
    minimum: int


def ranks() -> tuple[Rank, ...]:
    """Return the practice ranks, lowest first, named by the language catalogue."""
    return tuple(
        Rank(rank_id, title, hint, minimum)
        for (rank_id, title, hint), minimum in zip(
            messages_for().practice_ranks, RANK_THRESHOLDS, strict=True
        )
    )


def rank_for(looks: int) -> tuple[Rank, Rank | None, float]:
    """Return the rank of a number of looks, the next one, and the way to it (0 to 1)."""
    ladder = ranks()
    current = ladder[0]
    for rank in ladder:
        if looks >= rank.minimum:
            current = rank
    following = next((rank for rank in ladder if rank.minimum > looks), None)
    if following is None:
        return current, None, 1.0
    progress = (looks - current.minimum) / (following.minimum - current.minimum)
    return current, following, progress


def local_day(moment: datetime, zone: ZoneInfo) -> date:
    return moment.astimezone(zone).date()


def first_by_day(moments: Sequence[datetime], zone: ZoneInfo) -> dict[date, datetime]:
    """Return the first moment of each local day."""
    days: dict[date, datetime] = {}
    for moment in sorted(moments):
        days.setdefault(local_day(moment, zone), moment)
    return days


def streak(days: set[date], today: date) -> tuple[int, int, date | None]:
    """Return the current run, the best run and the last day with a look."""
    if not days:
        return 0, 0, None
    best = run = 0
    previous: date | None = None
    for day in sorted(days):
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        best = max(best, run)
        previous = day
    last = max(days)
    current = run if today - last <= timedelta(days=1) else 0
    return current, best, last


def recent_days(days: set[date], today: date) -> list[tuple[date, bool]]:
    """Return the last seven days, today first, and whether each had a look."""
    return [
        (today - timedelta(days=offset), today - timedelta(days=offset) in days)
        for offset in range(RECENT_DAYS)
    ]


def sky_position(concept: str) -> tuple[float, float]:
    """Return where a concept's star sits, from its name only: the same name, the same place."""
    digest = hashlib.sha256(concept.encode("utf-8")).digest()
    span = 1 - 2 * SKY_MARGIN
    x = SKY_MARGIN + span * int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
    y = SKY_MARGIN + span * int.from_bytes(digest[4:8], "big") / 0xFFFFFFFF
    return round(x, 4), round(y, 4)


@dataclass(frozen=True)
class Star:
    concept: str
    count: int
    first_seen: datetime


def sky(completions: Sequence[tuple[datetime, str]]) -> list[Star]:
    """Return one star per concept, in the order the concepts were first met."""
    seen: dict[str, list[datetime]] = {}
    for moment, concept in sorted(completions):
        name = concept.strip()
        if name:
            seen.setdefault(name, []).append(moment)
    return [Star(name, len(moments), moments[0]) for name, moments in seen.items()]


def quest_days(log: PracticeLog, zone: ZoneInfo) -> dict[date, datetime]:
    """Return the days the daily quest was done, with the moment it was."""
    looks = first_by_day(log.looks, zone)
    done = first_by_day([moment for moment, _concept in log.completions], zone)
    return {day: max(looks[day], done[day]) for day in sorted(set(looks) & set(done))}


def _nth(moments: Sequence[datetime], count: int) -> datetime | None:
    ordered = sorted(moments)
    return ordered[count - 1] if len(ordered) >= count else None


def _streak_reached(log: PracticeLog, zone: ZoneInfo, length: int) -> datetime | None:
    firsts = first_by_day(log.looks, zone)
    run = 0
    previous: date | None = None
    for day in sorted(firsts):
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        previous = day
        if run >= length:
            return firsts[day]
    return None


def _both_tutorial(log: PracticeLog) -> datetime | None:
    if all(slug in log.tutorial for slug in TUTORIAL_SLUGS):
        return max(log.tutorial[slug] for slug in TUTORIAL_SLUGS)
    return None


def _tenth_concept(log: PracticeLog) -> datetime | None:
    stars = sky(log.completions)
    return stars[9].first_seen if len(stars) >= 10 else None


def _first_quest(log: PracticeLog, zone: ZoneInfo) -> datetime | None:
    days = quest_days(log, zone)
    return min(days.values()) if days else None


BadgeRule = Callable[[PracticeLog, ZoneInfo], datetime | None]

BADGE_RULES: dict[str, BadgeRule] = {
    "first-look": lambda log, _zone: _nth(log.looks, 1),
    "seven-looks": lambda log, _zone: _nth(log.looks, 7),
    "thirty-looks": lambda log, _zone: _nth(log.looks, 30),
    "both-insights": lambda log, _zone: _both_tutorial(log),
    "first-action": lambda log, _zone: _nth(log.actions, 1),
    "first-place": lambda log, _zone: _nth(log.places, 1),
    "first-treasure": lambda log, _zone: _nth(log.treasures, 1),
    "ten-concepts": lambda log, _zone: _tenth_concept(log),
    "asked": lambda log, _zone: _nth(log.questions, 1),
    "streak-3": lambda log, zone: _streak_reached(log, zone, 3),
    "streak-7": lambda log, zone: _streak_reached(log, zone, 7),
    "daily-quest": _first_quest,
}


def badges(log: PracticeLog, zone: ZoneInfo) -> dict[str, datetime | None]:
    """Return every badge with the moment its rule first held, or None while it is locked."""
    return {badge_id: rule(log, zone) for badge_id, rule in BADGE_RULES.items()}
