from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from mockdata import cli, output
from mockdata.activity import Knobs, make_activity, parse
from mockdata.catalogue import Photo
from mockdata.members import EMAIL_DOMAIN, NameFactory, make_members
from mockdata.output import MockFile
from mockdata.places import COUNTRIES, City, Gazetteer, haversine_km

from .conftest import NOW

KNOBS = Knobs(insights=300, posts=150, follows=500, reactions=800, comments=200, map_entries=80)


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
    }  # fmt: skip


def Member_fields() -> list[str]:  # noqa: N802
    return list(output.Member.model_fields)


def test_handles_stay_unique_and_padded() -> None:
    names = NameFactory("x")
    taken = {"a" * 3}
    names._latin.user_name = lambda: "A"  # type: ignore[method-assign]
    first, second = names.handle(taken), names.handle(taken)
    assert first == "axx"
    assert second == "axx2"


def test_display_name_skips_latin_locales_and_blocked_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names = NameFactory("y")
    assert not names.display_name("EG").isascii()  # ar_EG answers in Latin script
    faker = names._faker("ar_SA")
    monkeypatch.setattr(faker, "last_name", lambda: "بن لادن")
    # The blocked part is never returned: another locale answers.
    assert "لادن" not in names.display_name("SA")


def test_display_name_fails_when_no_locale_speaks_arabic(monkeypatch: pytest.MonkeyPatch) -> None:
    names = NameFactory("z")
    for locale in ("ar_PS", "ar_SA", "ar_AA"):
        monkeypatch.setattr(names._faker(locale), "first_name", lambda: "Latin")
    with pytest.raises(RuntimeError, match="no Arabic name"):
        names.display_name("MA")


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
    assert max(uses.values()) <= 3
    pairs = [(i.image, country[i.member]) for i in file.insights]
    assert len(pairs) == len(set(pairs))


def test_insights_are_capped_by_the_catalogue(gazetteer: Gazetteer) -> None:
    few = [Photo(1, "cat.jpg", "cat", 1, 1)]
    file = generate(gazetteer, few)
    assert len(file.insights) == 3
    assert [i.placepix_id for i in file.images] == [1]


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
        "map_entries", "follows", "reactions", "comments",
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
