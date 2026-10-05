"""Insights, posts, follows, reactions, comment slots and atlas entries."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from mockdata.catalogue import Photo
from mockdata.output import (
    Comment,
    Follow,
    Insight,
    MapEntry,
    Member,
    Post,
    Reaction,
    stamp,
)
from mockdata.places import Gazetteer, draw_point

MAX_PHOTO_USES = 3
SAME_COUNTRY_SHARE = 0.6
REPLY_SHARE = 0.3
# Decision 61: «انتفعتُ بها» and «جزاك الله خيرًا», one of each per member and post.
REACTION_KINDS = ("benefited", "jazak")
_LOGNORMAL_SIGMA = 1.0


@dataclass(frozen=True)
class Knobs:
    insights: int = 2000
    posts: int = 1200
    follows: int = 15000
    reactions: int = 30000
    comments: int = 4000
    map_entries: int = 900


@dataclass(frozen=True)
class Activity:
    insights: list[Insight]
    posts: list[Post]
    map_entries: list[MapEntry]
    follows: list[Follow]
    reactions: list[Reaction]
    comments: list[Comment]


def parse(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=None)


def between(rng: random.Random, start: datetime, end: datetime) -> datetime:
    """A moment in [start, end]; the start when the window is empty."""
    span = int((end - start).total_seconds())
    return start + timedelta(seconds=rng.randrange(span + 1) if span > 0 else 0)


def _weights(rng: random.Random, count: int) -> list[float]:
    return [rng.lognormvariate(0.0, _LOGNORMAL_SIGMA) for _ in range(count)]


def make_insights(
    rng: random.Random,
    members: list[Member],
    photos: list[Photo],
    gazetteer: Gazetteer,
    count: int,
    now: datetime,
) -> list[Insight]:
    """Prolific and quiet members; a photo at most three times and once per country."""
    weights = _weights(rng, len(members))
    uses = dict.fromkeys((p.id for p in photos), 0)
    countries: dict[int, set[str]] = {p.id: set() for p in photos}
    ordered = sorted(photos, key=lambda p: p.id)
    out: list[Insight] = []
    for member in rng.choices(members, weights=weights, k=count):
        free = [
            p
            for p in ordered
            if uses[p.id] < MAX_PHOTO_USES and member.country not in countries[p.id]
        ]
        if not free:
            continue
        photo = rng.choice(free)
        uses[photo.id] += 1
        countries[photo.id].add(member.country)
        place = rng.choice(gazetteer.places[member.city_geoname_id])
        created = between(rng, parse(member.joined_at), now - timedelta(minutes=5))
        done = created + timedelta(seconds=rng.randrange(15, 90))
        out.append(
            Insight(
                ref="",
                member=member.ref,
                image=photo.id,
                created_at=stamp(created),
                completed_at=stamp(done),
                point=draw_point(rng, place),
            )
        )
    out.sort(key=lambda i: (i.created_at, i.member, i.image))
    return [i.model_copy(update={"ref": f"i{n:05d}"}) for n, i in enumerate(out, start=1)]


def make_posts(
    rng: random.Random, insights: list[Insight], count: int, now: datetime
) -> list[Post]:
    chosen = sorted(rng.sample(insights, min(count, len(insights))), key=lambda i: i.ref)
    posts = [
        Post(
            ref="",
            insight=i.ref,
            published_at=stamp(
                between(
                    rng,
                    parse(i.completed_at) + timedelta(minutes=1),
                    min(parse(i.completed_at) + timedelta(days=3), now),
                )
            ),
        )
        for i in chosen
    ]
    posts.sort(key=lambda p: (p.published_at, p.insight))
    return [p.model_copy(update={"ref": f"p{n:05d}"}) for n, p in enumerate(posts, start=1)]


def make_map_entries(
    rng: random.Random, posts: list[Post], count: int, now: datetime
) -> list[MapEntry]:
    chosen = sorted(rng.sample(posts, min(count, len(posts))), key=lambda p: p.ref)
    return [
        MapEntry(
            insight=p.insight,
            published_at=stamp(
                between(
                    rng, parse(p.published_at), min(parse(p.published_at) + timedelta(days=2), now)
                )
            ),
        )
        for p in chosen
    ]


def make_follows(
    rng: random.Random, members: list[Member], count: int, now: datetime
) -> list[Follow]:
    """Followers by activity, followed by popularity, mostly inside one country."""
    popularity = _weights(rng, len(members))
    activity = _weights(rng, len(members))
    by_country: dict[str, list[int]] = {}
    for idx, m in enumerate(members):
        by_country.setdefault(m.country, []).append(idx)
    seen: set[tuple[int, int]] = set()
    out: list[Follow] = []
    attempts = 0
    while len(out) < count and attempts < count * 20:
        attempts += 1
        src = rng.choices(range(len(members)), weights=activity)[0]
        pool = by_country[members[src].country] if rng.random() < SAME_COUNTRY_SHARE else None
        if pool is None:
            dst = rng.choices(range(len(members)), weights=popularity)[0]
        else:
            dst = rng.choices(pool, weights=[popularity[i] for i in pool])[0]
        if src == dst or (src, dst) in seen:
            continue
        seen.add((src, dst))
        start = max(parse(members[src].joined_at), parse(members[dst].joined_at))
        out.append(
            Follow(
                from_=members[src].ref,
                to=members[dst].ref,
                at=stamp(between(rng, start, now)),
            )
        )
    out.sort(key=lambda f: (f.at, f.from_, f.to))
    return out


def make_reactions(
    rng: random.Random,
    members: list[Member],
    posts: list[Post],
    author_of: dict[str, str],
    count: int,
    now: datetime,
) -> list[Reaction]:
    """Reactions after the post time, by active members, towards popular posts and authors."""
    if not posts:
        return []
    joined = {m.ref: parse(m.joined_at) for m in members}
    post_weights = _weights(rng, len(posts))
    member_weights = _weights(rng, len(members))
    seen: set[tuple[str, str]] = set()
    out: list[Reaction] = []
    attempts = 0
    while len(out) < count and attempts < count * 20:
        attempts += 1
        post = rng.choices(posts, weights=post_weights)[0]
        member = rng.choices(members, weights=member_weights)[0]
        if member.ref == author_of[post.ref] or (post.ref, member.ref) in seen:
            continue
        seen.add((post.ref, member.ref))
        start = max(parse(post.published_at), joined[member.ref])
        out.append(
            Reaction(
                post=post.ref,
                member=member.ref,
                kind=rng.choice(REACTION_KINDS),
                at=stamp(between(rng, start, now)),
            )
        )
    out.sort(key=lambda r: (r.at, r.post, r.member))
    return out


def _ref_of(refs: dict[int, str], index: int | None) -> str | None:
    return None if index is None else refs[index]


def make_comments(
    rng: random.Random,
    members: list[Member],
    posts: list[Post],
    count: int,
    now: datetime,
) -> list[Comment]:
    """Comment slots, texts left empty; a reply answers a top-level comment of the same post."""
    if not posts:
        return []
    joined = {m.ref: parse(m.joined_at) for m in members}
    post_weights = _weights(rng, len(posts))
    drafts: list[tuple[datetime, str, str, int | None]] = []
    times: list[datetime] = []
    top_by_post: dict[str, list[int]] = {}
    for n in range(count):
        post = rng.choices(posts, weights=post_weights)[0]
        member = rng.choice(members)
        parents = top_by_post.get(post.ref, [])
        parent = rng.choice(parents) if parents and rng.random() < REPLY_SHARE else None
        floor = (
            times[parent] + timedelta(seconds=1) if parent is not None else parse(post.published_at)
        )
        when = between(rng, max(floor, joined[member.ref]), now)
        times.append(when)
        drafts.append((when, post.ref, member.ref, parent))
        if parent is None:
            top_by_post.setdefault(post.ref, []).append(n)
    order = sorted(range(count), key=lambda n: (drafts[n][0], n))
    refs = {n: f"c{rank:05d}" for rank, n in enumerate(order, start=1)}
    return [
        Comment(
            ref=refs[n],
            post=drafts[n][1],
            member=drafts[n][2],
            parent=_ref_of(refs, drafts[n][3]),
            at=stamp(drafts[n][0]),
        )
        for n in order
    ]


def make_activity(
    seed: int,
    members: list[Member],
    photos: list[Photo],
    gazetteer: Gazetteer,
    knobs: Knobs,
    now: datetime,
) -> Activity:
    insights = make_insights(
        random.Random(f"{seed}:insights"), members, photos, gazetteer, knobs.insights, now
    )
    posts = make_posts(random.Random(f"{seed}:posts"), insights, knobs.posts, now)
    entries = make_map_entries(random.Random(f"{seed}:map"), posts, knobs.map_entries, now)
    owner = {i.ref: i.member for i in insights}
    author_of = {p.ref: owner[p.insight] for p in posts}
    return Activity(
        insights=insights,
        posts=posts,
        map_entries=entries,
        follows=make_follows(random.Random(f"{seed}:follows"), members, knobs.follows, now),
        reactions=make_reactions(
            random.Random(f"{seed}:reactions"), members, posts, author_of, knobs.reactions, now
        ),
        comments=make_comments(
            random.Random(f"{seed}:comments"), members, posts, knobs.comments, now
        ),
    )
