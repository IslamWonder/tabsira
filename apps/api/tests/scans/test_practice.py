"""Practice, never piety: the pure rules of ranks, streak, quest, sky and badges."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src import messages
from src.services import practice
from src.services.practice import PracticeLog

UTC_ZONE = ZoneInfo("UTC")
RIYADH = ZoneInfo("Asia/Riyadh")


def at(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 10, day, hour, tzinfo=UTC)


@pytest.mark.parametrize(
    ("looks", "rank", "following", "progress"),
    [
        (0, "nazir", "mutaammil", 0.0),
        (2, "nazir", "mutaammil", 2 / 3),
        (3, "mutaammil", "mustabsir", 0.0),
        (10, "mustabsir", "basir", 0.0),
        (20, "mustabsir", "basir", 0.5),
        (30, "basir", None, 1.0),
        (99, "basir", None, 1.0),
    ],
)
def test_ranks_count_looks_only(looks, rank, following, progress):
    current, after, way = practice.rank_for(looks)

    assert current.id == rank
    assert (after.id if after else None) == following
    assert way == pytest.approx(progress)


def test_the_ranks_carry_their_arabic_names():
    assert [rank.title for rank in practice.RANKS] == ["ناظر", "متأمّل", "مستبصر", "بصير بالتمرين"]
    assert [rank.minimum for rank in practice.RANKS] == [0, 3, 10, 30]


def test_a_missed_day_resets_the_current_run_never_the_best():
    days = {date(2026, 10, d) for d in (1, 2, 3, 5, 6)}

    assert practice.streak(set(), date(2026, 10, 6)) == (0, 0, None)
    assert practice.streak(days, date(2026, 10, 6)) == (2, 3, date(2026, 10, 6))
    assert practice.streak(days, date(2026, 10, 7)) == (2, 3, date(2026, 10, 6))
    assert practice.streak(days, date(2026, 10, 8)) == (0, 3, date(2026, 10, 6))


def test_the_day_is_the_learners_own():
    late = datetime(2026, 10, 4, 22, tzinfo=UTC)

    assert practice.local_day(late, UTC_ZONE) == date(2026, 10, 4)
    assert practice.local_day(late, RIYADH) == date(2026, 10, 5)
    assert practice.first_by_day([at(4, 15), at(4, 9), at(5)], UTC_ZONE) == {
        date(2026, 10, 4): at(4, 9),
        date(2026, 10, 5): at(5),
    }


def test_the_last_seven_days_today_first():
    days = practice.recent_days({date(2026, 10, 4), date(2026, 10, 1)}, date(2026, 10, 4))

    assert days[0] == (date(2026, 10, 4), True)
    assert days[3] == (date(2026, 10, 1), True)
    assert [looked for _, looked in days].count(True) == 2
    assert len(days) == 7


def test_a_star_sits_where_its_name_puts_it_and_grows_with_repeats():
    stars = practice.sky([(at(2), "الإحياء"), (at(1), "الشكر"), (at(3), "الإحياء"), (at(4), "  ")])

    assert [(star.concept, star.count, star.first_seen) for star in stars] == [
        ("الشكر", 1, at(1)),
        ("الإحياء", 2, at(2)),
    ]
    x, y = practice.sky_position("الإحياء")
    assert practice.sky_position("الإحياء") == (x, y)
    assert practice.sky_position("الشكر") != (x, y)
    assert 0.05 <= x <= 0.95
    assert 0.05 <= y <= 0.95


def test_the_daily_quest_is_a_look_and_a_completion_on_the_same_day():
    log = PracticeLog(
        looks=[at(4, 9), at(5, 9)],
        completions=[(at(4, 10), "أ"), (at(6, 10), "ب")],
    )

    assert practice.quest_days(log, UTC_ZONE) == {date(2026, 10, 4): at(4, 10)}


def test_a_new_learner_holds_no_badge():
    assert set(practice.badges(PracticeLog(), UTC_ZONE).values()) == {None}
    assert set(practice.BADGE_RULES) == set(messages.BADGES)


def test_each_badge_records_when_its_rule_first_held():
    looks = [at(1), at(2), at(3), at(3, 18), *[at(10 + n % 9) for n in range(30)]]
    log = PracticeLog(
        looks=looks,
        completions=[(at(1, 13 + n), f"معنى {n}") for n in range(10)],
        tutorial={"drop": at(2), "planting": at(5)},
        actions=[at(6)],
        places=[at(1, 13)],
        treasures=[at(8)],
        questions=[at(7)],
    )

    earned = practice.badges(log, UTC_ZONE)

    assert earned["first-look"] == at(1)
    assert earned["seven-looks"] == sorted(looks)[6]
    assert earned["thirty-looks"] == sorted(looks)[29]
    assert earned["both-insights"] == at(5)
    assert earned["first-action"] == at(6)
    assert earned["first-place"] == at(1, 13)
    assert earned["first-treasure"] == at(8)
    assert earned["ten-concepts"] == at(1, 22)
    assert earned["asked"] == at(7)
    assert earned["streak-3"] == at(3)
    assert earned["streak-7"] == at(16)
    assert earned["daily-quest"] == at(1, 13)


def test_a_badge_waits_for_its_whole_rule():
    log = PracticeLog(looks=[at(1), at(3)], tutorial={"drop": at(2)})

    earned = practice.badges(log, UTC_ZONE)

    assert earned["both-insights"] is None
    assert earned["streak-3"] is None
    assert earned["ten-concepts"] is None


def test_an_old_streak_still_counts_as_reached():
    log = PracticeLog(looks=[at(1) + timedelta(days=n) for n in range(3)])

    assert practice.badges(log, UTC_ZONE)["streak-3"] == at(3)
