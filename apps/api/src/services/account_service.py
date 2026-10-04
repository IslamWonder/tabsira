"""Everything an account owns: exporting it, and deleting it."""

from __future__ import annotations

import logging
import uuid

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock
from src.models.consent import Consent
from src.models.learning import LearnerUnitState
from src.models.scan import ChatMessage, Insight, Scan
from src.models.session import Session
from src.models.timeseries import EvidenceExposure
from src.models.user import OAuthAccount, User
from src.models.world import Treasure, WorldPlace
from src.scans import buffer
from src.schemas.account import AccountExport, LearningExport
from src.schemas.cookie_consent import CookieConsentExport
from src.schemas.profile import ConsentOut, ProfileOut
from src.services import atlas_service, cookie_consent_service, profile_service, social_export

log = logging.getLogger("tabsira.account")


async def export_learning(db: AsyncSession, user_id: uuid.UUID) -> LearningExport:
    """Collect what the scan workflow keeps for an account: no photo, scripture by reference."""
    scans = (
        await db.scalars(select(Scan).where(Scan.user_id == user_id).order_by(Scan.created_at))
    ).all()
    insights = (
        await db.scalars(
            select(Insight).where(Insight.user_id == user_id).order_by(Insight.created_at)
        )
    ).all()
    messages = (
        await db.scalars(
            select(ChatMessage)
            .join(Insight, Insight.id == ChatMessage.insight_id)
            .where(Insight.user_id == user_id)
            .order_by(ChatMessage.id)
        )
    ).all()
    places = (
        await db.scalars(
            select(WorldPlace).where(WorldPlace.user_id == user_id).order_by(WorldPlace.created_at)
        )
    ).all()
    treasures = (
        await db.scalars(
            select(Treasure)
            .join(Insight, Insight.id == Treasure.insight_id)
            .where(Insight.user_id == user_id)
            .order_by(Treasure.created_at)
        )
    ).all()
    units = (
        await db.scalars(
            select(LearnerUnitState)
            .where(LearnerUnitState.user_id == user_id)
            .order_by(LearnerUnitState.unit_id)
        )
    ).all()
    exposures = (
        await db.scalars(
            select(EvidenceExposure)
            .where(EvidenceExposure.user_id == user_id)
            .order_by(EvidenceExposure.at)
        )
    ).all()
    return LearningExport.model_validate(
        {
            "scans": scans,
            "insights": insights,
            "chat_messages": messages,
            "places": places,
            "treasures": treasures,
            "learner_units": units,
            "exposures": exposures,
        },
        from_attributes=True,
    )


async def export_account(db: AsyncSession, user: User) -> AccountExport:
    """
    Collect everything the user owns.

    Add every table that gets a user id to this function and to `delete_account`.
    The mailed link tokens are left out on purpose: they are stored only as
    hashes, expire within a day, and say nothing the user does not already have.
    """
    profile = await profile_service.ensure_profile(db, user.id)
    oauth_accounts = (
        await db.scalars(select(OAuthAccount).where(OAuthAccount.user_id == user.id))
    ).all()
    sessions = (await db.scalars(select(Session).where(Session.user_id == user.id))).all()
    consents = (
        await db.scalars(
            select(Consent).where(Consent.user_id == user.id).order_by(Consent.created_at)
        )
    ).all()
    return AccountExport.model_validate(
        {
            "exported_at": clock.utcnow(),
            "user": user,
            "oauth_accounts": oauth_accounts,
            "sessions": sessions,
            "profile": ProfileOut.model_validate(profile),
            "consents": [ConsentOut.model_validate(consent) for consent in consents],
            "cookie_consents": [
                CookieConsentExport.model_validate(choice)
                for choice in await cookie_consent_service.choices_of(db, user)
            ],
            "social": await social_export.collect(db, user),
            "map_entries": await atlas_service.list_mine(db, user),
            "learning": await export_learning(db, user.id),
        },
        from_attributes=True,
    )


async def delete_account(db: AsyncSession, user: User, *, redis: Redis) -> None:
    """
    Delete the user and, by ON DELETE CASCADE, everything that references them.

    Sessions, linked identities, the profile, the consent history, the cookie
    choices made while signed in, the mailed tokens, everything on the social
    network (posts with their publications, comments, follows, blocks, likes,
    bookmarks and reports), and the scans, insights, chat, world, treasures and
    learner state all go with the row. The cookie-consent table is append-only,
    and its guard lets exactly this cascade through. The evidence exposures name
    the user without a foreign key and are deleted here; the photos still in the
    temporary store are deleted from Redis first (they would expire within the
    hour anyway). Anything a later feature stores outside the database (photos in
    object storage) must be removed here too.
    """
    scan_ids = (await db.scalars(select(Scan.id).where(Scan.user_id == user.id))).all()
    try:
        for scan_id in scan_ids:
            await buffer.drop(redis, scan_id)
    except RedisError:
        log.warning("the photos of a deleted account stay until they expire: Redis is down")
    await db.execute(delete(EvidenceExposure).where(EvidenceExposure.user_id == user.id))
    await db.execute(delete(User).where(User.id == user.id))
