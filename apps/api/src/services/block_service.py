"""
Who is cut off from whom.

A block hides each of the two from the other, whoever placed it: neither sees the other's
posts, comments or profile, neither can follow or react to the other, and any follow between
them in either direction ends. A block that worked one way would tell the blocked person
exactly who blocked them and leave the blocker reading someone they wanted gone.

Every surface asks the same two questions of this module, so "blocked" cannot come to mean
one thing in the feed and another under a post. A blocked person is answered with "not
found", exactly as for something that does not exist.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import CompoundSelect, delete, select, union
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.social import Block, Follow
from src.models.user import User


def blocked_with(user_id: uuid.UUID) -> CompoundSelect[tuple[uuid.UUID]]:
    """Select the ids of everyone `user_id` has blocked or is blocked by."""
    return union(
        select(Block.blocked_id).where(Block.blocker_id == user_id),
        select(Block.blocker_id).where(Block.blocked_id == user_id),
    )


async def are_blocked(db: AsyncSession, first: uuid.UUID, second: uuid.UUID) -> bool:
    """Whether a block stands between the two accounts, in either direction."""
    found = await db.scalar(
        select(Block.blocker_id)
        .where(
            ((Block.blocker_id == first) & (Block.blocked_id == second))
            | ((Block.blocker_id == second) & (Block.blocked_id == first))
        )
        .limit(1)
    )
    return found is not None


async def block(db: AsyncSession, blocker: User, target: User) -> None:
    """Block `target`; the follows between the two, in both directions, end with it."""
    await db.execute(
        insert(Block)
        .values(blocker_id=blocker.id, blocked_id=target.id)
        .on_conflict_do_nothing(index_elements=[Block.blocker_id, Block.blocked_id])
    )
    # Left in place they would do nothing while the block stands and come back to life on an
    # unblock: someone blocked for a day would be followed again without either choosing it.
    await db.execute(
        delete(Follow).where(
            ((Follow.follower_id == blocker.id) & (Follow.followee_id == target.id))
            | ((Follow.follower_id == target.id) & (Follow.followee_id == blocker.id))
        )
    )


async def unblock(db: AsyncSession, blocker: User, target: User) -> None:
    """Lift the caller's own block; one placed the other way stays."""
    await db.execute(
        delete(Block).where(Block.blocker_id == blocker.id, Block.blocked_id == target.id)
    )


async def blocked_accounts(db: AsyncSession, blocker: User) -> Sequence[User]:
    """List the accounts the caller has blocked, newest block first."""
    rows = await db.scalars(
        select(User)
        .join(Block, Block.blocked_id == User.id)
        .where(Block.blocker_id == blocker.id)
        .order_by(Block.created_at.desc(), User.id.desc())
    )
    return rows.all()
