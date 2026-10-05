from __future__ import annotations

import argparse
import itertools
import json
import random
import re
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from mockdata import activity, cli, output
from mockdata.activity import MAX_PHOTO_USES, Knobs, make_activity, parse
from mockdata.catalogue import Photo
from mockdata.members import EMAIL_DOMAIN, NameFactory, make_members
from mockdata.names import FAMILY, FAMILY_BY_COUNTRY, FEMALE, MALE
from mockdata.output import MockFile
from mockdata.places import COUNTRIES, City, Gazetteer, Place, haversine_km

from .conftest import NOW

KNOBS = Knobs(
    insights=300,
    posts=150,
    follows=500,
    reactions=800,
    comments=200,
    map_entries=80,
    bookmarks=300,
    blocks=10,
)


def cities_of(gazetteer: Gazetteer) -> dict[str, list[City]]:
    out: dict[str, list[City]] = {}
    for c in gazetteer.cities:
        out.setdefault(c.country, []).append(c)
    return out


def generate(gazetteer: Gazetteer, photos: list[Photo], seed: int = 42) -> MockFile:
    args = argparse.Namespace(seed=seed, members=220, **vars(KNOBS))
    return cli.build(args, photos, gazetteer, NOW)


def test_members_shape(gazetteer: Gazetteer) -> None:
    members = make_members(1, 220, NOW, cities_of(gazetteer))
    assert len(members) == 220
    assert len({m.handle for m in members}) == 220
    assert Counter(m.country for m in members) == dict.fromkeys(COUNTRIES, 10)
    for m in members:
        assert 3 <= len(m.handle) <= 30
        assert m.email == f"{m.handle}@{EMAIL_DOMAIN}"
        assert NOW - timedelta(days=184) <= parse(m.joined_at) <= NOW
        assert not m.display_name.isascii()
    assert set(Member_fields()) == {
        "ref", "handle", "display_name", "email", "country", "city_geoname_id", "joined_at",
        "gender", "age_range", "goals", "knowledge_level", "religious_background", "theme",
        "reduced_motion", "sound", "public_full_name",
    }  # fmt: skip


def Member_fields() -> list[str]:  # noqa: N802
    return list(output.Member.model_fields)


def test_the_first_name_fits_the_declared_gender_and_the_handle_reads_like_it(
    gazetteer: Gazetteer,
) -> None:
    members = make_members(1, 220, NOW, cities_of(gazetteer))
    men, women = [a for a, _ in MALE], [a for a, _ in FEMALE]
    families = {a for a, _ in FAMILY}

    def split(name: str, firsts: list[str]) -> bool:
        return any(
            name.startswith(f"{first} ") and name[len(first) + 1 :] in families for first in firsts
        )

    seen = Counter(m.gender for m in members)
    assert set(seen) == {"man", "woman", "unknown"}
    assert seen["man"] > 60
    assert seen["woman"] > 60
    for m in members:
        firsts = {"man": men, "woman": women}.get(m.gender, men + women)
        assert split(m.display_name, firsts)
        assert re.fullmatch(r"[a-z][a-z0-9_]{2,29}", m.handle)


def test_the_profile_is_complete_varied_and_never_a_child(gazetteer: Gazetteer) -> None:
    members = make_members(1, 220, NOW, cities_of(gazetteer))
    assert {m.age_range for m in members} <= {"18_24", "25_39", "40_59", "60_plus", "unknown"}
    assert len({m.theme for m in members}) == 3
    assert len({m.knowledge_level for m in members}) >= 4
    assert {m.religious_background for m in members} == {"muslim", "unknown", "non_muslim"}
    assert any(m.public_full_name for m in members) and not all(m.public_full_name for m in members)
    assert any(m.sound for m in members)
    assert all(1 <= len(m.goals) <= 3 for m in members)


def test_the_cities_and_the_dates_do_not_depend_on_the_names(gazetteer: Gazetteer) -> None:
    one = make_members(1, 220, NOW, cities_of(gazetteer))
    two = make_members(1, 220, NOW, cities_of(gazetteer))
    assert one == two
    assert {m.ref: (m.country, m.city_geoname_id, m.joined_at) for m in one} == {
        m.ref: (m.country, m.city_geoname_id, m.joined_at) for m in two
    }


@pytest.mark.parametrize(
    ("draw", "first", "family", "expected"),
    [
        (0.1, "amal", "harbi", "amal_harbi"),
        (0.5, "amal", "harbi", "amal55"),
        (0.9, "amal", "harbi", "aharbi55"),
        (0.1, "", "", "_xx"),
        (0.1, "x" * 40, "y", "x" * 26),
    ],
)
def test_a_handle_reads_like_the_name_and_fits_the_limits(
    draw: float, first: str, family: str, expected: str
) -> None:
    names = NameFactory("x")
    names._rng.random = lambda: draw  # type: ignore[method-assign]
    names._rng.randrange = lambda *_: 55  # type: ignore[method-assign]
    assert names.handle(first, family, set()) == expected


def test_a_taken_handle_gets_a_number() -> None:
    names = NameFactory("x")
    names._rng.random = lambda: 0.1  # type: ignore[method-assign]
    taken = {"amal_harbi", "amal_harbi2"}
    assert names.handle("amal", "harbi", taken) == "amal_harbi3"
    assert "amal_harbi3" in taken


def test_two_runs_are_byte_identical(
    gazetteer: Gazetteer, photos: list[Photo], tmp_path: Path
) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    output.write(a, generate(gazetteer, photos))
    output.write(b, generate(gazetteer, photos))
    assert a.read_bytes() == b.read_bytes()
    output.write(tmp_path / "c.json", generate(gazetteer, photos, seed=43))
    assert (tmp_path / "c.json").read_bytes() != a.read_bytes()


def test_photo_reuse_rule(gazetteer: Gazetteer, photos: list[Photo]) -> None:
    file = generate(gazetteer, photos)
    country = {m.ref: m.country for m in file.members}
    uses = Counter(i.image for i in file.insights)
    assert max(uses.values()) <= MAX_PHOTO_USES
    # Sixty photos and 300 insights: a free country is always found, so none repeats.
    pairs = [(i.image, country[i.member]) for i in file.insights]
    assert len(pairs) == len(set(pairs))


def test_a_photo_spreads_its_uses_over_months(gazetteer: Gazetteer) -> None:
    file = generate(gazetteer, [Photo(1, "cat.jpg", "cat", 1, 1)])
    months = Counter(i.created_at[:7] for i in file.insights)
    assert len(months) >= 4
    assert max(months.values()) <= 3


def test_insights_are_capped_by_the_photos(gazetteer: Gazetteer) -> None:
    few = [Photo(1, "cat.jpg", "cat", 1, 1)]
    file = generate(gazetteer, few)
    assert len(file.insights) == MAX_PHOTO_USES
    assert [i.placepix_id for i in file.images] == [1]


def test_a_country_repeats_a_photo_only_when_no_other_is_free() -> None:
    one_country = Gazetteer(
        (City(1, "A", "أ", 10.0, 20.0, "TN", 100_000),), {1: (Place(10, 10.0, 20.0),)}
    )
    members = [
        output.Member(
            ref=f"m{n}",
            handle=f"h{n}",
            display_name="اسم",
            email=f"h{n}@{EMAIL_DOMAIN}",
            country="TN",
            city_geoname_id=1,
            joined_at="2026-04-05T10:00:00Z",
            gender="man",
            age_range="25_39",
            goals=["reflection"],
            knowledge_level="general",
            religious_background="muslim",
            theme="system",
            reduced_motion="system",
            sound=False,
            public_full_name=False,
        )
        for n in range(30)
    ]
    file_insights = make_activity(
        42, members, [Photo(1, "cat.jpg", "cat", 1, 1)], one_country, KNOBS, NOW
    ).insights
    assert len(file_insights) == MAX_PHOTO_USES


def test_the_members_and_the_follows_do_not_depend_on_the_photos(
    gazetteer: Gazetteer, photos: list[Photo]
) -> None:
    small, large = generate(gazetteer, photos[:10]), generate(gazetteer, photos)
    assert small.members == large.members
    assert small.follows == large.follows


def test_the_library_insight_is_carried(gazetteer: Gazetteer, photos: list[Photo]) -> None:
    args = argparse.Namespace(seed=42, members=220, **vars(KNOBS))
    file = cli.build(args, photos, gazetteer, NOW, {photos[0].id: {"insight": {"title": "t"}}})
    carried = {i.placepix_id: i.insight for i in file.images}
    assert carried[photos[0].id] == {"title": "t"}
    assert carried[photos[1].id] is None


def test_points_are_close_to_a_real_place_of_the_members_city(
    gazetteer: Gazetteer, photos: list[Photo]
) -> None:
    file = generate(gazetteer, photos)
    city_of = {m.ref: m.city_geoname_id for m in file.members}
    for insight in file.insights:
        lng, lat = insight.point
        nearest = min(
            haversine_km(p.latitude, p.longitude, lat, lng)
            for p in gazetteer.places[city_of[insight.member]]
        )
        assert nearest <= 1.5


def test_graph_rules(gazetteer: Gazetteer, photos: list[Photo]) -> None:
    file = generate(gazetteer, photos)
    insights = {i.ref: i for i in file.insights}
    posts = {p.ref: p for p in file.posts}
    joined = {m.ref: parse(m.joined_at) for m in file.members}
    now = NOW

    assert {p.insight for p in file.posts} <= set(insights)
    assert {e.insight for e in file.map_entries} <= {p.insight for p in file.posts}
    for i in file.insights:
        assert joined[i.member] <= parse(i.created_at) < parse(i.completed_at) <= now
    for p in file.posts:
        assert parse(p.published_at) > parse(insights[p.insight].completed_at)
        assert parse(p.published_at) <= now
    published = {p.insight: p.published_at for p in file.posts}
    for e in file.map_entries:
        assert e.published_at >= published[e.insight]
    for r in file.reactions:
        assert parse(r.at) >= parse(posts[r.post].published_at)
        assert parse(r.at) >= joined[r.member]
        assert parse(r.at) <= now
        assert insights[posts[r.post].insight].member != r.member
    keys = [(f.from_, f.to) for f in file.follows]
    assert len(keys) == len(set(keys))
    assert all(a != b for a, b in keys)
    by_ref = {c.ref: c for c in file.comments}
    assert len(by_ref) == len(file.comments)
    replies = [c for c in file.comments if c.parent]
    assert replies
    for c in replies:
        assert c.parent is not None
        parent = by_ref[c.parent]
        assert parent.parent is None  # one level deep
        assert parent.post == c.post
        assert parse(c.at) > parse(parent.at)
    for c in file.comments:
        assert parse(c.at) >= parse(posts[c.post].published_at)
        assert c.text is None


def test_follows_prefer_popular_members_and_the_same_country(
    gazetteer: Gazetteer, photos: list[Photo]
) -> None:
    file = generate(gazetteer, photos)
    country = {m.ref: m.country for m in file.members}
    same = sum(country[f.from_] == country[f.to] for f in file.follows)
    assert same / len(file.follows) > 0.5
    targets = Counter(f.to for f in file.follows)
    assert max(targets.values()) > 3 * (len(file.follows) / len(file.members))


def test_nothing_to_react_to_without_posts(gazetteer: Gazetteer, photos: list[Photo]) -> None:
    members = make_members(1, 220, NOW, cities_of(gazetteer))
    quiet = Knobs(insights=50, posts=0, follows=10, reactions=10, comments=10, map_entries=0)
    activity = make_activity(1, members, photos, gazetteer, quiet, NOW)
    assert activity.posts == []
    assert activity.reactions == []
    assert activity.comments == []
    assert activity.map_entries == []


def test_schema(gazetteer: Gazetteer, photos: list[Photo], tmp_path: Path) -> None:
    file = generate(gazetteer, photos)
    path = tmp_path / "out" / "f.json"
    output.write(path, file)
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    assert data["version"] == 1
    assert data["seed"] == 42
    assert data["generated_at"] == "2026-10-05T10:00:00Z"
    assert set(data) == {
        "version", "seed", "generated_at", "images", "members", "insights", "posts",
        "map_entries", "follows", "blocks", "reactions", "bookmarks", "comments",
    }  # fmt: skip
    assert set(data["images"][0]) == {
        "placepix_id", "url", "filename", "category", "width", "height", "scene", "insight",
    }  # fmt: skip
    assert all(i["insight"] is None for i in data["images"])
    assert all(len(i["url"]) <= 64 for i in data["images"])
    assert set(data["follows"][0]) == {"from", "to", "at"}
    assert all(p["reflection"] is None for p in data["posts"])
    assert all(c["text"] is None for c in data["comments"])
    assert "\\u" not in text  # Arabic stays UTF-8, never escaped
    assert text.endswith("}\n")
    assert (
        json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n" == text
    )
    for i in data["insights"]:
        lng, lat = i["point"]
        assert -180 <= lng <= 180
        assert -90 <= lat <= 90


def test_unknown_fields_are_refused() -> None:
    with pytest.raises(ValueError, match="extra"):
        output.Post.model_validate(
            {"ref": "p1", "insight": "i1", "published_at": "x", "reflection": None, "gender": "x"}
        )


def test_parse_and_stamp_round_trip() -> None:
    assert output.stamp(parse("2026-10-05T10:00:00Z")) == "2026-10-05T10:00:00Z"
    assert isinstance(parse("2026-10-05T10:00:00Z"), datetime)


# ─── Every feature of the network (plan 23.5) ───


def big(gazetteer: Gazetteer, photos: list[Photo]) -> MockFile:
    args = argparse.Namespace(
        seed=7,
        members=220,
        **{**vars(KNOBS), "insights": 400, "posts": 400, "map_entries": 300, "follows": 1500},
    )
    return cli.build(args, photos, gazetteer, NOW)


def test_prolific_members_have_a_streak_of_consecutive_days(
    gazetteer: Gazetteer, photos: list[Photo]
) -> None:
    file = big(gazetteer, photos)
    joined = {m.ref: parse(m.joined_at) for m in file.members}
    days: dict[str, list[date]] = {}
    for i in file.insights:
        assert joined[i.member] <= parse(i.created_at) < parse(i.completed_at) <= NOW
        days.setdefault(i.member, []).append(parse(i.created_at).date())
    runs = []
    for member_days in days.values():
        ordered = sorted(set(member_days))
        best = streak = 1
        for before, after in itertools.pairwise(ordered):
            streak = streak + 1 if (after - before).days == 1 else 1
            best = max(best, streak)
        runs.append(best)
    assert max(runs) >= 3
    assert sum(1 for run in runs if run >= 3) >= 5


def test_a_streak_stops_at_the_day_a_member_joined() -> None:
    members = [
        output.Member(
            ref="m1",
            handle="amal_tn",
            display_name="أمل",
            email="a@x",
            country="TN",
            city_geoname_id=1,
            joined_at="2026-10-04T09:00:00Z",
            gender="woman",
            age_range="25_39",
            goals=[],
            knowledge_level="new",
            religious_background="muslim",
            theme="system",
            reduced_motion="system",
            sound=False,
            public_full_name=False,
        )
    ]
    rng = random.Random(1)
    insights = [
        output.Insight(
            ref=f"i{n}",
            member="m1",
            image=n,
            created_at="2026-10-04T10:00:00Z",
            completed_at="2026-10-04T10:01:00Z",
            point=(1.0, 2.0),
        )
        for n in range(5)
    ]
    activity._streaks(rng, members, insights, NOW)
    created = [parse(i.created_at) for i in insights]
    assert all(c >= parse("2026-10-04T09:01:00Z") for c in created)
    # A streak was possible for two days at most (the 4th and the 5th); the rest keep their time.
    assert sum(1 for c in created if c.date() == date(2026, 10, 4)) >= 3


def test_feedback_is_mostly_helpful_and_reasons_come_with_a_no(
    gazetteer: Gazetteer, photos: list[Photo]
) -> None:
    file = big(gazetteer, photos)
    rated = [i for i in file.insights if i.feedback is not None]
    assert 0.2 < len(rated) / len(file.insights) < 0.5
    assert any(not i.feedback.helpful for i in rated if i.feedback)
    for i in rated:
        assert i.feedback is not None
        assert (i.feedback.reasons == []) == i.feedback.helpful
        assert parse(i.completed_at) <= parse(i.feedback.at) <= NOW


def test_posts_are_public_or_followers_only_with_or_without_photo_and_reflection(
    gazetteer: Gazetteer, photos: list[Photo]
) -> None:
    file = big(gazetteer, photos)
    on_atlas = {e.insight for e in file.map_entries}
    assert {p.visibility for p in file.posts} == {"public", "followers"}
    assert any(not p.photo for p in file.posts)
    assert any(not p.reflect for p in file.posts)
    for p in file.posts:
        if p.insight in on_atlas:
            assert p.visibility == "public"
            assert p.photo
    private = {p.ref for p in file.posts if p.visibility == "followers"}
    assert private
    assert not {r.post for r in file.reactions} & private
    assert not {c.post for c in file.comments} & private
    assert not {b.post for b in file.bookmarks} & private


def test_a_tenth_of_the_entries_is_orphaned_and_half_of_those_are_sponsored(
    gazetteer: Gazetteer, photos: list[Photo]
) -> None:
    file = big(gazetteer, photos)
    owner = {i.ref: i.member for i in file.insights}
    joined = {m.ref: parse(m.joined_at) for m in file.members}
    orphaned = [e for e in file.map_entries if e.orphaned]
    sponsored = [e for e in orphaned if e.sponsor]
    assert len(orphaned) == round(len(file.map_entries) * 0.1)
    assert 0 < len(sponsored) <= len(orphaned)
    assert abs(len(sponsored) - len(orphaned) / 2) <= len(orphaned) * 0.15 + 1
    for e in orphaned:
        assert parse(e.published_at) <= NOW - timedelta(days=35)
    for e in sponsored:
        assert e.sponsor is not None
        assert e.sponsor.member != owner[e.insight]
        at = parse(e.sponsor.at)
        assert at >= parse(e.published_at) + timedelta(days=31)
        assert joined[e.sponsor.member] <= at <= NOW
        assert e.sponsor.reflection is None
    assert all(e.sponsor is None for e in file.map_entries if not e.orphaned)


def test_nobody_is_found_to_sponsor_when_no_other_member_had_joined() -> None:
    member = output.Member(
        ref="m1",
        handle="amal_tn",
        display_name="أمل",
        email="a@x",
        country="TN",
        city_geoname_id=1,
        joined_at="2026-01-01T09:00:00Z",
        gender="woman",
        age_range="25_39",
        goals=[],
        knowledge_level="new",
        religious_background="muslim",
        theme="system",
        reduced_motion="system",
        sound=False,
        public_full_name=False,
    )
    entries = [
        output.MapEntry(insight=f"i{n}", published_at="2026-02-01T10:00:00Z") for n in range(20)
    ]
    owner = {e.insight: "m1" for e in entries}
    out = activity.make_orphans(random.Random(1), [member], entries, owner, NOW)
    assert [e.orphaned for e in out].count(True) == 2
    assert all(e.sponsor is None for e in out)
    young = [
        output.MapEntry(insight=f"i{n}", published_at="2026-10-01T10:00:00Z") for n in range(20)
    ]
    assert activity.make_orphans(random.Random(1), [member], young, owner, NOW) == young


def test_bookmarks_are_saved_after_the_post_by_other_members(
    gazetteer: Gazetteer, photos: list[Photo]
) -> None:
    file = big(gazetteer, photos)
    posts = {p.ref: p for p in file.posts}
    owner = {i.ref: i.member for i in file.insights}
    keys = [(b.post, b.member) for b in file.bookmarks]
    assert file.bookmarks
    assert len(keys) == len(set(keys))
    for b in file.bookmarks:
        assert owner[posts[b.post].insight] != b.member
        assert parse(posts[b.post].published_at) <= parse(b.at) <= NOW


def test_blocks_never_touch_a_popular_author_or_contradict_the_graph(
    gazetteer: Gazetteer, photos: list[Photo]
) -> None:
    file = big(gazetteer, photos)
    owner = {i.ref: i.member for i in file.insights}
    author_of = {p.ref: owner[p.insight] for p in file.posts}
    taken = activity.interacting_pairs(
        file.follows,
        file.reactions,
        file.bookmarks,
        file.comments,
        file.map_entries,
        author_of,
        owner,
    )
    followers = Counter(f.to for f in file.follows)
    popular = {ref for ref, _ in followers.most_common(activity.POPULAR_BLOCK_EXEMPT)}
    assert file.blocks
    for b in file.blocks:
        assert b.from_ != b.to
        assert {b.from_, b.to}.isdisjoint(popular)
        assert frozenset((b.from_, b.to)) not in taken


def test_blocks_need_at_least_two_members_outside_the_popular() -> None:
    assert activity.make_blocks(random.Random(1), [], [], set(), 5, NOW) == []


def test_no_public_post_means_no_bookmark() -> None:
    private = [
        output.Post(
            ref="p1", insight="i1", published_at="2026-02-01T10:00:00Z", visibility="followers"
        )
    ]
    assert activity.make_bookmarks(random.Random(1), [], private, {"p1": "m1"}, 5, NOW) == []


def test_a_photo_with_a_verse_and_a_hadith_is_used_most(gazetteer: Gazetteer) -> None:
    both = Photo(1, "a.jpg", "cat", 1, 1, activity.USES_VERSE_AND_HADITH)
    verse = Photo(2, "b.jpg", "cat", 1, 1, activity.USES_VERSE_ONLY)
    hadith = Photo(3, "c.jpg", "cat", 1, 1, activity.USES_HADITH_ONLY)
    file = generate(gazetteer, [both, verse, hadith])
    uses = Counter(i.image for i in file.insights)
    assert uses == {1: 7, 2: 4, 3: 3}


def test_the_uses_follow_the_evidence_of_the_insight() -> None:
    assert cli.max_uses_of({"quran": {"surah": 1}, "hadith": {"number": "1"}}) == 7
    assert cli.max_uses_of({"quran": {"surah": 1}, "hadith": None}) == 4
    assert cli.max_uses_of({"quran": None, "hadith": {"number": "1"}}) == 3


def test_the_family_name_belongs_to_the_members_country(gazetteer: Gazetteer) -> None:
    members = make_members(1, 220, NOW, cities_of(gazetteer))
    for m in members:
        families = {a for a, _ in FAMILY_BY_COUNTRY[m.country]}
        assert any(m.display_name.endswith(f" {family}") for family in families)
