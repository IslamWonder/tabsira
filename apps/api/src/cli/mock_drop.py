"""
Remove some mock insights whole, with everything that hangs on them (plan 23).

`--refresh-insights` rewrites the imported mock insights from a newer file; when the newer file
has no insight any more for a photo (the pipeline, run again, found no fitting text), the mock
insights of that photo go, with their scans, posts and publications, atlas entries, reactions,
comments, bookmarks, sponsorships and the reports that name them.

Only mock accounts' insights are removed. A real member's row that hangs on them is counted
first and only removed with `--also-dependent-rows`, as for `--clean`.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Select, and_, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.mock_accounts import MOCK_DOMAINS
from src.models.atlas import MapEntry, MapEntrySponsorship
from src.models.scan import Insight, Scan
from src.models.social import (
    Bookmark,
    Comment,
    InsightPublication,
    Post,
    PostReaction,
    Report,
    ReportTarget,
)
from src.models.timeseries import AiCall, EvidenceExposure
from src.models.user import User


@dataclass(frozen=True)
class DropReport:
    """What a drop removed, and the rows of real members that went with it."""

    insights: int = 0
    posts: int = 0
    entries: int = 0
    dependents: dict[str, int] = field(default_factory=dict)


class DependentRowsError(Exception):
    """Real members' rows hang on the insights to drop, and the caller did not allow removing them."""


def mock_users() -> Select[uuid.UUID]:
    """Select the ids of the mock accounts."""
    return select(User.id).where(or_(*(User.email.endswith(f"@{d}") for d in MOCK_DOMAINS)))


async def _count(db: AsyncSession, model: Any, *conditions: Any) -> int:
    return int(await db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)


def _reports(
    posts: Select[Any], comments: Select[Any], entries: Select[Any]
) -> ColumnElement[bool]:
    sponsorships = select(MapEntrySponsorship.id).where(MapEntrySponsorship.entry_id.in_(entries))
    return or_(
        and_(Report.target_type == ReportTarget.POST, Report.target_id.in_(posts)),
        and_(Report.target_type == ReportTarget.COMMENT, Report.target_id.in_(comments)),
        and_(Report.target_type == ReportTarget.MAP_ENTRY, Report.target_id.in_(entries)),
        and_(Report.target_type == ReportTarget.SPONSORSHIP, Report.target_id.in_(sponsorships)),
    )


async def _dependents(
    db: AsyncSession, posts: Select[Any], entries: Select[Any], comments: Select[Any]
) -> dict[str, int]:
    people = select(User.id).where(~User.id.in_(mock_users()))
    found = {
        "comments or replies": await _count(
            db, Comment, Comment.author_id.in_(people), Comment.post_id.in_(posts)
        ),
        "reactions": await _count(
            db, PostReaction, PostReaction.user_id.in_(people), PostReaction.post_id.in_(posts)
        ),
        "bookmarks": await _count(
            db, Bookmark, Bookmark.user_id.in_(people), Bookmark.post_id.in_(posts)
        ),
        "sponsorships": await _count(
            db,
            MapEntrySponsorship,
            MapEntrySponsorship.user_id.in_(people),
            MapEntrySponsorship.entry_id.in_(entries),
        ),
        "reports": await _count(
            db, Report, Report.reporter_id.in_(people), _reports(posts, comments, entries)
        ),
    }
    return {kind: number for kind, number in found.items() if number}


async def drop_insights(
    db: AsyncSession, insight_ids: Collection[int], *, also_dependent_rows: bool = False
) -> DropReport:
    """
    Delete the mock insights among `insight_ids` and every row that hangs on them.

    Without `also_dependent_rows`, real members' rows among them refuse the drop
    (`DependentRowsError`) and nothing is removed.
    """
    if not insight_ids:
        return DropReport()
    ids = list(
        (
            await db.scalars(
                select(Insight.id).where(
                    Insight.id.in_(list(insight_ids)), Insight.user_id.in_(mock_users())
                )
            )
        ).all()
    )
    if not ids:
        return DropReport()
    publications = select(InsightPublication.id).where(InsightPublication.insight_id.in_(ids))
    posts = select(Post.id).where(Post.publication_id.in_(publications))
    comments = select(Comment.id).where(Comment.post_id.in_(posts))
    entries = select(MapEntry.id).where(MapEntry.insight_id.in_(ids))
    dependents = await _dependents(db, posts, entries, comments)
    if dependents and not also_dependent_rows:
        counts = ", ".join(f"{kind} {number}" for kind, number in dependents.items())
        message = (
            f"rows of other members hang on the mock insights to remove ({counts}): "
            "nothing was changed; pass --also-dependent-rows to remove them too"
        )
        raise DependentRowsError(message)
    report = DropReport(
        insights=len(ids),
        posts=await _count(db, Post, Post.id.in_(posts)),
        entries=await _count(db, MapEntry, MapEntry.id.in_(entries)),
        dependents=dependents,
    )
    scans = list((await db.scalars(select(Insight.scan_id).where(Insight.id.in_(ids)))).all())
    await db.execute(delete(Report).where(_reports(posts, comments, entries)))
    # Comments, reactions and bookmarks go with their post; points, cells and sponsorships with
    # their entry; the world's treasures, threads and reveals with their insight.
    await db.execute(delete(Post).where(Post.id.in_(posts)))
    await db.execute(delete(InsightPublication).where(InsightPublication.insight_id.in_(ids)))
    await db.execute(delete(EvidenceExposure).where(EvidenceExposure.insight_id.in_(ids)))
    await db.execute(delete(AiCall).where(AiCall.insight_id.in_(ids)))
    await db.execute(delete(Insight).where(Insight.id.in_(ids)))
    await db.execute(
        delete(Scan).where(Scan.id.in_(scans), ~exists().where(Insight.scan_id == Scan.id))
    )
    return report
