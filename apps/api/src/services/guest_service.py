"""
Guests: what a browser without an account keeps on the server, and how it joins an account.

The guest cookie carries 256 random bits and an HMAC of them under the server
key, so a value the server did not issue is refused before any lookup. The
database keeps only the SHA-256 of the random part (`guests.key`), so a copy of
the database cannot be turned back into a cookie. A guest unseen for
GUEST_TTL_DAYS is deleted with everything it saved (ON DELETE CASCADE, plus the
learner rows that name it without a foreign key), by the next guest created:
there is no scheduled job. At the first sign-in from that browser the guest's
scans, insights, world, chat and learning state move to the account
(`merge_into_user`) and the cookie is cleared.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock, security
from src.config import Settings
from src.models import (
    EvidenceExposure,
    Guest,
    Insight,
    LearnerUnitState,
    Scan,
    Treasure,
    WorldPlace,
    WorldRelation,
)

SIGNATURE_PURPOSE = "guest-cookie"
# `last_seen_at` is written at most this often.
TOUCH_INTERVAL = timedelta(hours=1)
# A cookie longer than token, dot and signature is not looked at.
COOKIE_MAX = 160


def key_of(token: str) -> str:
    """Return the stored key of a cookie token: the hex SHA-256 of its random part."""
    return hashlib.sha256(token.encode()).hexdigest()


def _signature(settings: Settings, token: str) -> str:
    return security.keyed_hash(settings.hash_key, SIGNATURE_PURPOSE, token)


def cookie_value(settings: Settings, token: str) -> str:
    return f"{token}.{_signature(settings, token)}"


def cookie_token(request: Request, settings: Settings) -> str | None:
    """Return the random part of a guest cookie the server signed, or None."""
    value = request.cookies.get(settings.guest_cookie_name)
    if not value or len(value) > COOKIE_MAX:
        return None
    token, _, signature = value.rpartition(".")
    if not token or not hmac.compare_digest(signature, _signature(settings, token)):
        return None
    return token


def set_cookie(response: Response, settings: Settings, token: str) -> None:
    """Attach the guest cookie: httpOnly, Secure, SameSite=Lax, on the session cookie's domain."""
    response.set_cookie(
        settings.guest_cookie_name,
        cookie_value(settings, token),
        max_age=int(settings.guest_ttl.total_seconds()),
        path="/",
        domain=settings.session_cookie_domain or None,
        secure=True,
        httponly=True,
        samesite="lax",
    )


def clear_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.guest_cookie_name,
        path="/",
        domain=settings.session_cookie_domain or None,
        secure=True,
        httponly=True,
        samesite="lax",
    )


def _expired_before(settings: Settings) -> datetime:
    return clock.utcnow() - settings.guest_ttl


async def find(db: AsyncSession, settings: Settings, token: str) -> Guest | None:
    """Return the live guest of a token, touching it at most once an hour."""
    guest = await db.get(Guest, key_of(token))
    if guest is None or guest.last_seen_at < _expired_before(settings):
        return None
    now = clock.utcnow()
    if now - guest.last_seen_at >= TOUCH_INTERVAL:
        guest.last_seen_at = now
        await db.flush()
    return guest


async def create(db: AsyncSession, settings: Settings) -> tuple[str, Guest]:
    """Make a new guest and return the token its cookie will carry, which exists nowhere else."""
    await purge_expired(db, settings)
    token = security.new_token()
    now = clock.utcnow()
    guest = Guest(key=key_of(token), created_at=now, last_seen_at=now)
    db.add(guest)
    await db.flush()
    return token, guest


async def purge_expired(db: AsyncSession, settings: Settings) -> int:
    """Delete the guests unseen for GUEST_TTL_DAYS and everything they saved; return how many."""
    expired = list(
        await db.scalars(select(Guest.key).where(Guest.last_seen_at < _expired_before(settings)))
    )
    if expired:
        await _delete_unlinked_rows(db, expired)
        await db.execute(delete(Guest).where(Guest.key.in_(expired)))
    return len(expired)


async def _delete_unlinked_rows(db: AsyncSession, keys: list[str]) -> None:
    """Delete the learner rows that name a guest without a foreign key to it."""
    await db.execute(delete(LearnerUnitState).where(LearnerUnitState.guest_key.in_(keys)))
    await db.execute(delete(EvidenceExposure).where(EvidenceExposure.guest_key.in_(keys)))


async def merge_into_user(db: AsyncSession, key: str, user_id: uuid.UUID) -> bool:
    """
    Move everything a guest saved to an account, then delete the guest; say whether it existed.

    A place the account already has absorbs the guest's place of the same
    region (its insights, treasures and threads move to it); learner unit rows
    are added together.
    """
    if await db.get(Guest, key) is None:
        return False
    await _merge_places(db, key, user_id)
    for model in (Scan, Insight):
        await db.execute(
            update(model)
            .where(model.guest_key == key)
            .values(user_id=user_id, guest_key=None)
            .execution_options(synchronize_session=False)
        )
    await db.execute(
        update(EvidenceExposure)
        .where(EvidenceExposure.guest_key == key)
        .values(user_id=user_id, guest_key=None)
        .execution_options(synchronize_session=False)
    )
    await _merge_learner_states(db, key, user_id)
    await db.execute(delete(Guest).where(Guest.key == key))
    await db.flush()
    return True


async def _merge_places(db: AsyncSession, key: str, user_id: uuid.UUID) -> None:
    guest_places = list(await db.scalars(select(WorldPlace).where(WorldPlace.guest_key == key)))
    for place in guest_places:
        kept: WorldPlace | None = await db.scalar(
            select(WorldPlace).where(
                WorldPlace.user_id == user_id, WorldPlace.region_id == place.region_id
            )
        )
        if kept is None:
            place.user_id, place.guest_key = user_id, None
            continue
        await db.execute(
            update(Insight).where(Insight.place_id == place.id).values(place_id=kept.id)
        )
        await db.execute(
            update(Treasure).where(Treasure.place_id == place.id).values(place_id=kept.id)
        )
        await _move_relations(db, place.id, kept.id)
        if place.last_visited_at and (
            kept.last_visited_at is None or place.last_visited_at > kept.last_visited_at
        ):
            kept.last_visited_at = place.last_visited_at
        await db.delete(place)
    await db.flush()


async def _move_relations(db: AsyncSession, old: int, new: int) -> None:
    """
    Re-point the threads of a merged place; a thread that already exists is dropped.

    A guest's thread joins two guest places of different regions, so its other
    end is never the account's place of this region.
    """
    relations = list(
        await db.scalars(
            select(WorldRelation).where(
                (WorldRelation.place_a_id == old) | (WorldRelation.place_b_id == old)
            )
        )
    )
    for relation in relations:
        other = relation.place_b_id if relation.place_a_id == old else relation.place_a_id
        await db.delete(relation)
        await db.flush()
        low, high = sorted([other, new])
        await db.execute(
            insert(WorldRelation)
            .values(
                place_a_id=low,
                place_b_id=high,
                reason=relation.reason,
                insight_a_id=relation.insight_a_id,
                insight_b_id=relation.insight_b_id,
            )
            .on_conflict_do_nothing(constraint="uq_world_relations_places_reason")
        )


async def _merge_learner_states(db: AsyncSession, key: str, user_id: uuid.UUID) -> None:
    rows = list(await db.scalars(select(LearnerUnitState).where(LearnerUnitState.guest_key == key)))
    for row in rows:
        statement = insert(LearnerUnitState).values(
            user_id=user_id,
            path_version=row.path_version,
            unit_id=row.unit_id,
            seen_count=row.seen_count,
            opened_count=row.opened_count,
            completed_count=row.completed_count,
            created_at=row.created_at,
            last_at=row.last_at,
        )
        excluded = statement.excluded
        await db.execute(
            statement.on_conflict_do_update(
                index_elements=[
                    LearnerUnitState.user_id,
                    LearnerUnitState.path_version,
                    LearnerUnitState.unit_id,
                ],
                index_where=LearnerUnitState.user_id.is_not(None),
                set_={
                    "seen_count": LearnerUnitState.seen_count + excluded.seen_count,
                    "opened_count": LearnerUnitState.opened_count + excluded.opened_count,
                    "completed_count": LearnerUnitState.completed_count + excluded.completed_count,
                    "created_at": func.least(LearnerUnitState.created_at, excluded.created_at),
                    "last_at": func.greatest(LearnerUnitState.last_at, excluded.last_at),
                },
            )
        )
    await db.execute(delete(LearnerUnitState).where(LearnerUnitState.guest_key == key))
