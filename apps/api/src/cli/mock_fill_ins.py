"""
Fill-ins: bring mock members already imported up to a feature added after their import (plan 23).

The mock file is imported once; a later feature that the mock data should show (a count, a
state, a new column) would otherwise stay empty on every mock row until a full `--clean` and a
new import, which renumbers every post and drops what real members left on them. A fill-in
writes just that feature onto the mock rows that are there:

    uv run python -m src.cli.import_mock --fill-in views --i-understand

Every fill-in touches mock rows only (accounts of `MOCK_DOMAINS`), is deterministic (the same
rows give the same values), and is safe to run again: it never lowers what real use has added.
A feature that the mock data should show adds its fill-in to `FILL_INS` and its section to
`tools/mockdata/README.md`, in the same commit as the generator change.
"""

from __future__ import annotations

import random
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import Select, func, or_, select, union, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.mock_accounts import MOCK_DOMAINS
from src.models.social import Bookmark, Comment, Post, PostReaction, PostStatus, PostVisibility
from src.models.user import User

# The numbers of `add_views` in tools/mockdata/src/mockdata/activity.py, so a post filled in here
# reads like one the generator wrote: readers per member who reacted, saved or commented, the
# log-mean and spread of the tail every post gets (median about 20), and the share of that reach
# a followers-only post keeps.
VIEWS_PER_ENGAGED = 8
VIEWS_LOG_MEAN = 3.0
VIEWS_LOG_SIGMA = 1.0
FOLLOWERS_ONLY_REACH = 0.3


@dataclass(frozen=True)
class FillIn:
    """One named fill-in: what it writes, and the function that writes it."""

    name: str
    summary: str
    run: Callable[[AsyncSession], Awaitable[int]]


def _mock_authors() -> Select[uuid.UUID]:
    on_mock_domain = or_(*(User.email.endswith(f"@{domain}") for domain in MOCK_DOMAINS))
    return select(User.id).where(on_mock_domain)


def plausible_views(post_id: int, engaged: int, *, public: bool) -> int:
    """Return the views a mock post shows: everyone who engaged, and many more who only read."""
    rng = random.Random(f"views:{post_id}")  # noqa: S311 - mock numbers, not a secret
    reach = VIEWS_PER_ENGAGED * engaged + rng.lognormvariate(VIEWS_LOG_MEAN, VIEWS_LOG_SIGMA)
    if not public:
        reach *= FOLLOWERS_ONLY_REACH
    return max(engaged, round(reach))


async def fill_views(db: AsyncSession) -> int:
    """Give every published mock post a plausible view count (task 16.3); return how many changed."""
    people = union(
        select(PostReaction.post_id, PostReaction.user_id),
        select(Bookmark.post_id, Bookmark.user_id),
        select(Comment.post_id, Comment.author_id),
    ).subquery()
    engaged = (
        select(people.c.post_id, func.count().label("people")).group_by(people.c.post_id).subquery()
    )
    rows = (
        await db.execute(
            select(
                Post.id,
                Post.visibility,
                Post.views_count,
                func.coalesce(engaged.c.people, 0),
            )
            .outerjoin(engaged, engaged.c.post_id == Post.id)
            .where(
                Post.status == PostStatus.PUBLISHED,
                Post.author_id.in_(_mock_authors()),
            )
            .order_by(Post.id)
        )
    ).all()
    changed = 0
    for post_id, visibility, current, people_count in rows:
        target = plausible_views(
            post_id, int(people_count), public=visibility == PostVisibility.PUBLIC
        )
        if target <= current:
            continue
        # A view is not an edit: `updated_at` keeps its value.
        await db.execute(
            update(Post)
            .where(Post.id == post_id)
            .values(views_count=target, updated_at=Post.updated_at)
            .execution_options(synchronize_session=False)
        )
        changed += 1
    return changed


FILL_INS: dict[str, FillIn] = {
    fill_in.name: fill_in
    for fill_in in (
        FillIn("views", "a plausible view count on every published mock post", fill_views),
    )
}
