"""
The owner's rating of an insight, and the admin's queue of them.

One row per insight, replaced when the owner answers again; a new answer opens it
again for review. The note is the owner's own words about their own insight: it is
kept with the insight, goes with it, and is read only by the owner and the team.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock
from src.models import FeedbackReason, FeedbackState, Insight, InsightFeedback
from src.schemas.insight import FeedbackIn, FeedbackOut


def describe(row: InsightFeedback | None) -> FeedbackOut | None:
    """Return the rating as the owner sees it, or None when there is none."""
    if row is None:
        return None
    return FeedbackOut(
        helpful=row.helpful,
        reasons=[FeedbackReason(reason) for reason in row.reasons],
        note=row.note,
        updated_at=row.updated_at,
    )


async def of_insight(db: AsyncSession, insight_id: int) -> InsightFeedback | None:
    """Return the insight's rating, if its owner gave one."""
    found: InsightFeedback | None = await db.scalar(
        select(InsightFeedback).where(InsightFeedback.insight_id == insight_id)
    )
    return found


async def rate(db: AsyncSession, insight: Insight, body: FeedbackIn) -> FeedbackOut:
    """Record or replace the owner's rating; a changed rating goes back to the review queue."""
    row = await of_insight(db, insight.id)
    if row is None:
        row = InsightFeedback(insight_id=insight.id)
        db.add(row)
    row.helpful = body.helpful
    row.reasons = [reason.value for reason in body.reasons]
    row.note = body.note
    row.state = FeedbackState.OPEN
    row.updated_at = clock.utcnow()
    await db.commit()
    out = describe(row)
    assert out is not None  # just written
    return out
