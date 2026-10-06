"""Insights, posts, follows, reactions, comment slots and atlas entries."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from mockdata.catalogue import Photo
from mockdata.output import (
    Block,
    Bookmark,
    Comment,
    Feedback,
    Follow,
    Insight,
    MapEntry,
    Member,
    Post,
    Reaction,
    Sponsor,
    stamp,
)
from mockdata.places import Gazetteer, draw_point

# About seven insights per photo: 150 photos give the 1000 members over a thousand insights.
MAX_PHOTO_USES = 7
USES_VERSE_AND_HADITH = MAX_PHOTO_USES
USES_VERSE_ONLY = 4
USES_HADITH_ONLY = 3
# Draws of a time before a photo's use may fall in a month it was already used in.
MONTH_TRIES = 6
SAME_COUNTRY_SHARE = 0.6
REPLY_SHARE = 0.3
# Decision 61: «انتفعتُ بها» and «جزاك الله خيرًا», one of each per member and post.
REACTION_KINDS = ("benefited", "jazak")
_LOGNORMAL_SIGMA = 1.0
# A member with this many insights may have a streak: one insight a day, on consecutive days.
STREAK_MIN = 3
STREAK_SHARE = 0.8
# Of those streaks, the share that is still alive (it ends in the last three days).
CURRENT_STREAK_SHARE = 0.6
FEEDBACK_SHARE = 0.35
HELPFUL_SHARE = 0.8
FEEDBACK_REASONS = ("wrong_text", "misread_scene", "wrong_explanation", "other")
# A post of an insight with no atlas entry may be for followers only, or show no photo.
FOLLOWERS_ONLY_SHARE = 0.5
NO_PHOTO_SHARE = 0.6
NO_REFLECTION_SHARE = 0.15
# Readers per member who reacted, saved or commented, the median of the tail every post gets
# (e^3, about 20), and the share of that reach a followers-only post keeps.
VIEWS_PER_ENGAGED = 8
VIEWS_LOG_MEAN = 3.0
FOLLOWERS_ONLY_REACH = 0.3
# «كفالة»: an entry quiet for 30 days is orphaned, so only an entry older than that can be.
ORPHAN_AFTER = timedelta(days=35)
ORPHAN_SHARE = 0.10
SPONSORED_SHARE = 0.5
SPONSOR_DELAY = timedelta(days=31)
POPULAR_BLOCK_EXEMPT = 100


@dataclass(frozen=True)
class Knobs:
    insights: int = 2000
    posts: int = 1200
    follows: int = 15000
    reactions: int = 30000
    comments: int = 4000
    map_entries: int = 900
    bookmarks: int = 6000
    blocks: int = 40


@dataclass(frozen=True)
class Activity:
    insights: list[Insight]
    posts: list[Post]
    map_entries: list[MapEntry]
    follows: list[Follow]
    blocks: list[Block]
    reactions: list[Reaction]
    bookmarks: list[Bookmark]
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
    """
    Prolific and quiet members; a photo at most its own `max_uses` times.

    A photo whose insight shows a verse and a hadith is used most, so those are drawn first.

    A photo goes to a country it has not been seen in when one is free, and its uses fall in
    different months when the member's months allow it, so the feed does not repeat itself.
    """
    weights = _weights(rng, len(members))
    uses = dict.fromkeys((p.id for p in photos), 0)
    countries: dict[int, set[str]] = {p.id: set() for p in photos}
    months: dict[int, set[str]] = {p.id: set() for p in photos}
    ordered = sorted(photos, key=lambda p: p.id)
    out: list[Insight] = []
    for member in rng.choices(members, weights=weights, k=count):
        free = [p for p in ordered if uses[p.id] < p.max_uses]
        if not free:
            continue
        elsewhere = [p for p in free if member.country not in countries[p.id]]
        pool = elsewhere or free
        photo = rng.choices(pool, weights=[p.max_uses - uses[p.id] for p in pool])[0]
        uses[photo.id] += 1
        countries[photo.id].add(member.country)
        place = rng.choice(gazetteer.places[member.city_geoname_id])
        created = _new_month(rng, parse(member.joined_at), now, months[photo.id])
        months[photo.id].add(created.strftime("%Y-%m"))
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
    _streaks(rng, members, out, now)
    out.sort(key=lambda i: (i.created_at, i.member, i.image))
    return [i.model_copy(update={"ref": f"i{n:05d}"}) for n, i in enumerate(out, start=1)]


def _streaks(rng: random.Random, members: list[Member], out: list[Insight], now: datetime) -> None:
    """
    Give the members with several insights a streak: one a day, on consecutive days.

    The newest insight falls on the streak's last day, in the last three days for a streak that
    is still alive. A day before the member joined ends the streak there; the insights it does not
    reach keep their times. The photo-month rule of `make_insights` is not kept for these.
    """
    joined = {m.ref: parse(m.joined_at) for m in members}
    last = now - timedelta(minutes=5)
    by_member: dict[str, list[int]] = {}
    for position, item in enumerate(out):
        by_member.setdefault(item.member, []).append(position)
    for ref in sorted(by_member):
        positions = sorted(by_member[ref], key=lambda p: out[p].created_at)
        if len(positions) < STREAK_MIN or rng.random() > STREAK_SHARE:
            continue
        ago = rng.randrange(3) if rng.random() < CURRENT_STREAK_SHARE else rng.randrange(3, 60)
        end = last.date() - timedelta(days=ago)
        for back, position in enumerate(reversed(positions)):
            start = datetime.combine(end - timedelta(days=back), time.min)
            low = max(start + timedelta(hours=6), joined[ref] + timedelta(minutes=1))
            high = min(start + timedelta(hours=23), last)
            if low > high:
                break
            created = between(rng, low, high)
            done = created + timedelta(seconds=rng.randrange(15, 90))
            out[position] = out[position].model_copy(
                update={"created_at": stamp(created), "completed_at": stamp(done)}
            )


def add_feedback(rng: random.Random, insights: list[Insight], now: datetime) -> list[Insight]:
    """A third of the members rate their insight: mostly helpful, now and then a reason it was not."""
    out: list[Insight] = []
    for item in insights:
        if rng.random() < FEEDBACK_SHARE:
            helpful = rng.random() < HELPFUL_SHARE
            reasons = [] if helpful else sorted(rng.sample(FEEDBACK_REASONS, rng.randint(1, 2)))
            at = min(parse(item.completed_at) + timedelta(minutes=rng.randrange(1, 40)), now)
            item = item.model_copy(  # noqa: PLW2901
                update={"feedback": Feedback(helpful=helpful, reasons=reasons, at=stamp(at))}
            )
        out.append(item)
    return out


def _new_month(rng: random.Random, joined: datetime, now: datetime, taken: set[str]) -> datetime:
    """A moment after `joined`, in a month not `taken` when a few draws find one."""
    created = between(rng, joined, now - timedelta(minutes=5))
    for _ in range(MONTH_TRIES):
        if created.strftime("%Y-%m") not in taken:
            break
        created = between(rng, joined, now - timedelta(minutes=5))
    return created


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


def shape_posts(rng: random.Random, posts: list[Post], entries: list[MapEntry]) -> list[Post]:
    """
    Some posts for followers only, some without a photo, some without a reflection.

    Only the post of an insight with no atlas entry is made private or photo-less: the entry shows
    the insight's photo to everyone, so the two would contradict each other.
    """
    on_atlas = {e.insight for e in entries}
    free = sorted(p.ref for p in posts if p.insight not in on_atlas)
    followers = set(rng.sample(free, round(len(free) * FOLLOWERS_ONLY_SHARE)))
    plain = set(rng.sample(free, round(len(free) * NO_PHOTO_SHARE)))
    return [
        p.model_copy(
            update={
                "visibility": "followers" if p.ref in followers else "public",
                "photo": p.ref not in plain,
                "reflect": rng.random() >= NO_REFLECTION_SHARE,
            }
        )
        for p in posts
    ]


def make_orphans(
    rng: random.Random,
    members: list[Member],
    entries: list[MapEntry],
    owner: dict[str, str],
    now: datetime,
) -> list[MapEntry]:
    """
    A tenth of the entries went quiet and were orphaned; half of those found a sponsor.

    Only an entry older than the 30 quiet days can be orphaned. The sponsor is another member who
    had joined by then; a few members sponsor many, as a few people look after many.
    """
    eligible = sorted(e.insight for e in entries if parse(e.published_at) <= now - ORPHAN_AFTER)
    chosen = rng.sample(eligible, min(round(len(entries) * ORPHAN_SHARE), len(eligible)))
    sponsored = set(chosen[: round(len(chosen) * SPONSORED_SHARE)])
    weights = _weights(rng, len(members))
    joined = {m.ref: parse(m.joined_at) for m in members}
    by_insight = {e.insight: e for e in entries}
    for insight in sorted(chosen):
        entry = by_insight[insight]
        sponsor = None
        if insight in sponsored:
            earliest = parse(entry.published_at) + SPONSOR_DELAY
            for _ in range(30):
                pick = rng.choices(members, weights=weights)[0]
                if pick.ref != owner[insight] and joined[pick.ref] <= earliest <= now:
                    when = between(rng, max(earliest, joined[pick.ref]), now - timedelta(hours=1))
                    sponsor = Sponsor(member=pick.ref, at=stamp(when))
                    break
        by_insight[insight] = entry.model_copy(update={"orphaned": True, "sponsor": sponsor})
    return [by_insight[e.insight] for e in entries]


def make_bookmarks(
    rng: random.Random,
    members: list[Member],
    posts: list[Post],
    author_of: dict[str, str],
    count: int,
    now: datetime,
) -> list[Bookmark]:
    """Saved posts: by active members, towards popular public posts, never one's own."""
    public = [p for p in posts if p.visibility == "public"]
    if not public:
        return []
    joined = {m.ref: parse(m.joined_at) for m in members}
    post_weights = _weights(rng, len(public))
    member_weights = _weights(rng, len(members))
    seen: set[tuple[str, str]] = set()
    out: list[Bookmark] = []
    attempts = 0
    while len(out) < count and attempts < count * 20:
        attempts += 1
        post = rng.choices(public, weights=post_weights)[0]
        member = rng.choices(members, weights=member_weights)[0]
        if member.ref == author_of[post.ref] or (post.ref, member.ref) in seen:
            continue
        seen.add((post.ref, member.ref))
        start = max(parse(post.published_at), joined[member.ref])
        out.append(Bookmark(post=post.ref, member=member.ref, at=stamp(between(rng, start, now))))
    out.sort(key=lambda b: (b.at, b.post, b.member))
    return out


def interacting_pairs(
    follows: list[Follow],
    reactions: list[Reaction],
    bookmarks: list[Bookmark],
    comments: list[Comment],
    entries: list[MapEntry],
    author_of: dict[str, str],
    owner: dict[str, str],
) -> set[frozenset[str]]:
    """Every two members who did something to each other or to each other's work."""
    pairs: set[frozenset[str]] = {frozenset((f.from_, f.to)) for f in follows}
    pairs |= {frozenset((r.member, author_of[r.post])) for r in reactions}
    pairs |= {frozenset((b.member, author_of[b.post])) for b in bookmarks}
    by_ref = {c.ref: c for c in comments}
    for c in comments:
        pairs.add(frozenset((c.member, author_of[c.post])))
        if c.parent is not None:
            pairs.add(frozenset((c.member, by_ref[c.parent].member)))
    pairs |= {frozenset((e.sponsor.member, owner[e.insight])) for e in entries if e.sponsor}
    return {pair for pair in pairs if len(pair) == 2}


def make_blocks(
    rng: random.Random,
    members: list[Member],
    follows: list[Follow],
    taken: set[frozenset[str]],
    count: int,
    now: datetime,
) -> list[Block]:
    """
    A few blocks between members who never met: none involves a popular author.

    The most followed members are left out, and so is any pair that follows, reacted, saved,
    commented or sponsored towards the other, so a block never contradicts what the file shows.
    """
    followers: dict[str, int] = {}
    for f in follows:
        followers[f.to] = followers.get(f.to, 0) + 1
    popular = {
        ref
        for ref, _ in sorted(followers.items(), key=lambda kv: (-kv[1], kv[0]))[
            :POPULAR_BLOCK_EXEMPT
        ]
    }
    pool = [m for m in members if m.ref not in popular]
    joined = {m.ref: parse(m.joined_at) for m in members}
    out: list[Block] = []
    seen: set[frozenset[str]] = set(taken)
    attempts = 0
    while len(out) < count and attempts < count * 50 and len(pool) > 1:
        attempts += 1
        a, b = rng.sample(pool, 2)
        pair = frozenset((a.ref, b.ref))
        if pair in seen:
            continue
        seen.add(pair)
        at = between(rng, max(joined[a.ref], joined[b.ref]), now)
        out.append(Block(from_=a.ref, to=b.ref, at=stamp(at)))
    out.sort(key=lambda x: (x.at, x.from_, x.to))
    return out


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


def add_views(
    rng: random.Random,
    posts: list[Post],
    reactions: list[Reaction],
    bookmarks: list[Bookmark],
    comments: list[Comment],
) -> list[Post]:
    """
    A view count for every post: everyone who engaged with it, and the many more who only read.

    Those who react, save or comment are a small share of readers, so the count is a multiple of
    them plus a long tail that guests and quiet members add; a followers-only post reaches fewer.
    Its own random stream, so nothing else of the file changes.
    """
    engaged: dict[str, set[str]] = {}
    pairs = [(r.post, r.member) for r in reactions]
    pairs += [(b.post, b.member) for b in bookmarks]
    pairs += [(c.post, c.member) for c in comments]
    for post_ref, member in pairs:
        engaged.setdefault(post_ref, set()).add(member)
    out = []
    for post in posts:
        people = len(engaged.get(post.ref, set()))
        reach = VIEWS_PER_ENGAGED * people + rng.lognormvariate(VIEWS_LOG_MEAN, _LOGNORMAL_SIGMA)
        if post.visibility != "public":
            reach *= FOLLOWERS_ONLY_REACH
        out.append(post.model_copy(update={"views": max(people, round(reach))}))
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
    insights = add_feedback(random.Random(f"{seed}:feedback"), insights, now)
    posts = make_posts(random.Random(f"{seed}:posts"), insights, knobs.posts, now)
    entries = make_map_entries(random.Random(f"{seed}:map"), posts, knobs.map_entries, now)
    posts = shape_posts(random.Random(f"{seed}:shapes"), posts, entries)
    owner = {i.ref: i.member for i in insights}
    entries = make_orphans(random.Random(f"{seed}:orphans"), members, entries, owner, now)
    author_of = {p.ref: owner[p.insight] for p in posts}
    # Followers-only posts take no reaction, save or comment from the public.
    public = [p for p in posts if p.visibility == "public"]
    follows = make_follows(random.Random(f"{seed}:follows"), members, knobs.follows, now)
    reactions = make_reactions(
        random.Random(f"{seed}:reactions"), members, public, author_of, knobs.reactions, now
    )
    bookmarks = make_bookmarks(
        random.Random(f"{seed}:bookmarks"), members, posts, author_of, knobs.bookmarks, now
    )
    comments = make_comments(
        random.Random(f"{seed}:comments"), members, public, knobs.comments, now
    )
    taken = interacting_pairs(follows, reactions, bookmarks, comments, entries, author_of, owner)
    posts = add_views(random.Random(f"{seed}:views"), posts, reactions, bookmarks, comments)
    return Activity(
        insights=insights,
        posts=posts,
        map_entries=entries,
        follows=follows,
        blocks=make_blocks(
            random.Random(f"{seed}:blocks"), members, follows, taken, knobs.blocks, now
        ),
        reactions=reactions,
        bookmarks=bookmarks,
        comments=comments,
    )
