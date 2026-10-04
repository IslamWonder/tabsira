"""The learner's practice, computed from what the database recorded (src/services/practice.py)."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock, messages
from src.models import (
    ActionState,
    ChatMessage,
    ChatStatus,
    Insight,
    InsightOrigin,
    Scan,
    ScanOutcome,
    ScanStatus,
    Treasure,
    WorldPlace,
)
from src.owner import Owner
from src.schemas.progress import (
    BadgeOut,
    CountsOut,
    DayOut,
    NextRankOut,
    ProgressOut,
    QuestOut,
    QuestStepOut,
    RankOut,
    SkyOut,
    StarOut,
    StreakOut,
)
from src.services import practice
from src.services.practice import PracticeLog


async def practice_log(db: AsyncSession, owner: Owner | None) -> PracticeLog:
    """Collect the owner's recorded events; a caller with no identity has none."""
    if owner is None:
        return PracticeLog()
    looks = (
        await db.scalars(
            select(Scan.finished_at)
            .where(
                owner.where(Scan),
                Scan.status == ScanStatus.DONE,
                Scan.outcome == ScanOutcome.INSIGHTS,
                Scan.finished_at.is_not(None),
            )
            .order_by(Scan.finished_at)
        )
    ).all()
    completed = (
        await db.scalars(
            select(Insight)
            .where(owner.where(Insight), Insight.completed_at.is_not(None))
            .order_by(Insight.completed_at)
        )
    ).all()
    places = (
        await db.scalars(
            select(WorldPlace.created_at)
            .where(owner.where(WorldPlace))
            .order_by(WorldPlace.created_at)
        )
    ).all()
    treasures = (
        await db.scalars(
            select(Treasure.revealed_at)
            .join(Insight, Insight.id == Treasure.insight_id)
            .where(owner.where(Insight), Treasure.revealed_at.is_not(None))
            .order_by(Treasure.revealed_at)
        )
    ).all()
    questions = (
        await db.scalars(
            select(ChatMessage.answered_at)
            .join(Insight, Insight.id == ChatMessage.insight_id)
            .where(owner.where(Insight), ChatMessage.status == ChatStatus.ANSWERED)
            .order_by(ChatMessage.answered_at)
        )
    ).all()
    actions = (
        await db.scalars(
            select(Insight.action_at)
            .where(owner.where(Insight), Insight.action_state == ActionState.DONE)
            .order_by(Insight.action_at)
        )
    ).all()
    return PracticeLog(
        looks=[moment for moment in looks if moment is not None],
        completions=[
            (row.completed_at, str(row.why.get("concept", "")))
            for row in completed
            if row.completed_at is not None
        ],
        tutorial={
            row.tutorial_slug: row.completed_at
            for row in completed
            if row.origin is InsightOrigin.TUTORIAL
            and row.tutorial_slug is not None
            and row.completed_at is not None
        },
        actions=[moment for moment in actions if moment is not None],
        places=list(places),
        treasures=[moment for moment in treasures if moment is not None],
        questions=[moment for moment in questions if moment is not None],
    )


def describe(log: PracticeLog, zone: ZoneInfo) -> ProgressOut:
    """Return the learner's practice as the page shows it, in the learner's own day."""
    today = practice.local_day(clock.utcnow(), zone)
    looks = len(log.looks)
    rank, following, way = practice.rank_for(looks)
    look_days = set(practice.first_by_day(log.looks, zone))
    current, best, last = practice.streak(look_days, today)
    completion_days = set(practice.first_by_day([moment for moment, _ in log.completions], zone))
    looked_today, completed_today = today in look_days, today in completion_days
    stars = practice.sky(log.completions)
    earned = practice.badges(log, zone)
    return ProgressOut(
        timezone=str(zone),
        rank=RankOut(
            id=rank.id,
            title=rank.title,
            hint=rank.hint,
            looks=looks,
            next=NextRankOut(id=following.id, title=following.title, minimum=following.minimum)
            if following
            else None,
            progress=round(way, 4),
        ),
        streak=StreakOut(
            current=current,
            best=best,
            last_day=last,
            days=[
                DayOut(day=day, looked=looked)
                for day, looked in practice.recent_days(look_days, today)
            ],
        ),
        daily_quest=QuestOut(
            title=messages.DAILY_QUEST_TITLE,
            day=today,
            steps=[
                QuestStepOut(
                    id="look", label=messages.DAILY_QUEST_STEPS["look"], done=looked_today
                ),
                QuestStepOut(
                    id="complete",
                    label=messages.DAILY_QUEST_STEPS["complete"],
                    done=completed_today,
                ),
            ],
            done=looked_today and completed_today,
            days_done=len(practice.quest_days(log, zone)),
        ),
        sky=SkyOut(
            count=len(stars),
            stars=[
                StarOut(
                    concept=star.concept,
                    count=star.count,
                    first_seen=star.first_seen,
                    x=practice.sky_position(star.concept)[0],
                    y=practice.sky_position(star.concept)[1],
                )
                for star in stars
            ],
        ),
        badges=[
            BadgeOut(
                id=badge_id,
                title=messages.BADGES[badge_id][0],
                description=messages.BADGES[badge_id][1],
                earned=moment is not None,
                earned_at=moment,
            )
            for badge_id, moment in earned.items()
        ],
        counts=CountsOut(
            looks=looks,
            completed=len(log.completions),
            actions_done=len(log.actions),
            places=len(log.places),
            treasures=len(log.treasures),
            questions=len(log.questions),
        ),
        disclaimer=messages.PRACTICE_DISCLAIMER,
    )
