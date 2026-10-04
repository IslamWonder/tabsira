"""The ranking of «لك»: every number is arithmetic a reader can be told."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.services import ranking
from src.services.ranking import Candidate

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
ANN, BOB, CAT = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def post(post_id, *, hours=1.0, author=BOB, name="بوب", concepts=()):
    return Candidate(
        post_id=post_id,
        author_id=author,
        author_name=name,
        published_at=NOW - timedelta(hours=hours),
        concepts=tuple(concepts),
    )


def order(candidates, **kwargs):
    options = {"now": NOW, "followed": set(), "seen": set(), "personalise": True} | kwargs
    return [row.candidate.post_id for row in ranking.rank(candidates, **options)]


def test_freshness_halves_every_day_and_never_goes_below_nothing_for_the_future():
    assert ranking.freshness(NOW, NOW) == 1.0
    assert ranking.freshness(NOW - timedelta(hours=24), NOW) == pytest.approx(0.5)
    assert ranking.freshness(NOW - timedelta(hours=48), NOW) == pytest.approx(0.25)
    assert ranking.freshness(NOW + timedelta(hours=5), NOW) == 1.0


def test_a_newer_post_ranks_above_an_older_one_and_a_tie_goes_to_the_newer_id():
    assert order([post(1, hours=30), post(2, hours=2), post(3, hours=10)]) == [2, 3, 1]
    assert order([post(5, hours=1), post(9, hours=1), post(7, hours=1)]) == [9, 7, 5]


def test_a_followed_author_is_lifted_but_only_when_personalised():
    older_followed = post(1, hours=20, author=ANN, name="آن")
    newer = post(2, hours=1)

    assert order([older_followed, newer], followed={ANN}) == [1, 2]
    assert order([older_followed, newer], followed={ANN}, personalise=False) == [2, 1]


def test_a_post_the_reader_has_met_is_pushed_down_but_only_when_personalised():
    met, fresh = post(1, hours=1), post(2, hours=10)

    assert order([met, fresh], seen={1}) == [2, 1]
    assert order([met, fresh], seen={1}, personalise=False) == [1, 2]


def test_the_same_concept_again_costs_a_step_each_time_up_to_a_cap():
    posts = [post(i, hours=i, concepts=("water",)) for i in range(1, 8)]
    scores = {
        r.candidate.post_id: r.score
        for r in ranking.rank(posts, now=NOW, followed=set(), seen=set(), personalise=True)
    }

    first = ranking.freshness(posts[0].published_at, NOW)
    assert scores[1] == pytest.approx(first, abs=1e-6)
    assert scores[2] == pytest.approx(
        ranking.freshness(posts[1].published_at, NOW) - 0.15, abs=1e-6
    )
    assert scores[7] == pytest.approx(ranking.freshness(posts[6].published_at, NOW) - 0.6, abs=1e-6)


def test_variety_lifts_a_different_topic_above_a_slightly_fresher_repeat():
    water_new = post(1, hours=1, concepts=("water",))
    water_again = post(2, hours=2, concepts=("water",))
    light = post(3, hours=4, concepts=("light",))

    assert order([water_new, water_again, light]) == [1, 3, 2]


def test_a_post_with_no_concepts_is_never_charged_for_variety():
    posts = [post(i, hours=i) for i in (1, 2, 3)]

    assert [
        r.score for r in ranking.rank(posts, now=NOW, followed=set(), seen=set(), personalise=True)
    ] == sorted([round(ranking.freshness(p.published_at, NOW), 6) for p in posts], reverse=True)


def reasons(candidates, **kwargs):
    options = {"now": NOW, "followed": set(), "seen": set(), "personalise": True} | kwargs
    return {
        r.candidate.post_id: (r.why.code, r.why.text) for r in ranking.rank(candidates, **options)
    }


def test_each_item_carries_the_reason_it_is_where_it_is():
    posts = [
        post(1, hours=100, author=ANN, name="آن"),
        post(2, hours=1),
        post(3, hours=100, concepts=("light",)),
        post(4, hours=100),
    ]

    found = reasons(posts, followed={ANN})

    assert found[1] == ("followed_author", "لأنك تتابع آن")
    assert found[2] == ("fresh", "بصيرة نُشرت قبل قليل")
    assert found[3] == ("new_topic", "لتنويع ما تقرؤه: موضوع مختلف عمّا قبله")
    assert found[4] == ("community", "من بصائر المجتمع")


def test_a_repeated_topic_is_not_called_new_and_follows_are_not_named_when_personalisation_is_off():
    posts = [
        post(1, hours=100, concepts=("light",)),
        post(2, hours=101, concepts=("light",), author=ANN, name="آن"),
    ]

    found = reasons(posts, followed={ANN}, personalise=False)

    assert found[1][0] == "new_topic"
    assert found[2][0] == "community"


def test_after_continues_strictly_past_the_cursor_and_equal_scores_split_on_the_id():
    rows = ranking.rank(
        [post(1, hours=1), post(2, hours=1), post(3, hours=1), post(4, hours=9)],
        now=NOW,
        followed=set(),
        seen=set(),
        personalise=True,
    )

    ids = [r.candidate.post_id for r in rows]
    assert ids == [3, 2, 1, 4]
    assert [r.candidate.post_id for r in ranking.after(rows, rows[1].score, 2)] == [1, 4]
    assert [r.candidate.post_id for r in ranking.after(rows, None, None)] == ids
    assert [r.candidate.post_id for r in ranking.after(rows, rows[3].score, 4)] == []


def test_the_ranking_reads_nothing_about_a_person():
    fields = set(Candidate.__dataclass_fields__)

    assert fields == {"post_id", "author_id", "author_name", "published_at", "concepts"}
