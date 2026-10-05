"""Everything an account owns: exporting it, and deleting it."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock
from src.errors import AppError, ErrorCode
from src.models.consent import Consent
from src.models.learning import LearnerUnitState
from src.models.scan import ChatMessage, ChatStatus, Insight, Scan
from src.models.session import Session
from src.models.timeseries import EvidenceExposure
from src.models.user import OAuthAccount, User
from src.models.world import Treasure, WorldPlace, WorldReveal
from src.scans import buffer
from src.schemas.account import AccountExport, LearningExport, PhotoExport
from src.schemas.cookie_consent import CookieConsentExport
from src.schemas.profile import ConsentOut, ProfileOut
from src.services import (
    atlas_service,
    cookie_consent_service,
    photo_service,
    profile_service,
    social_export,
    sponsorship_service,
)
from src.services.insight_view import answer_is_shown, shown_evidence, shown_ids
from src.storage.base import StorageError
from src.storage.photos import PhotoStore

log = logging.getLogger("tabsira.account")


async def _chat_export(
    db: AsyncSession, insights: Sequence[Insight], rows: Sequence[ChatMessage]
) -> list[dict[str, Any]]:
    """Keep every answer's text, and say which ones are no longer shown (right of access)."""
    shown: dict[int, set[str]] = {}
    for insight in insights:
        verse, hadith = await shown_evidence(db, insight)
        shown[insight.id] = shown_ids(verse, hadith)
    return [
        {
            "insight_id": row.insight_id,
            "question": row.question,
            "answer": row.answer,
            "level": row.level,
            "evidence_ids": row.evidence_ids,
            "withdrawn": row.status is ChatStatus.ANSWERED
            and not answer_is_shown(row, shown[row.insight_id]),
            "created_at": row.created_at,
        }
        for row in rows
    ]


async def export_learning(db: AsyncSession, user_id: uuid.UUID) -> LearningExport:
    """Collect what the scan workflow keeps: scripture by reference, kept photos by insight."""
    scans = (
        await db.scalars(
            select(Scan).where(Scan.user_id == user_id).order_by(Scan.created_at, Scan.id)
        )
    ).all()
    insights = (
        await db.scalars(
            select(Insight)
            .where(Insight.user_id == user_id)
            # Two insights of one scan share a creation time: the id keeps the order stable.
            .order_by(Insight.created_at, Insight.id)
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
            select(WorldPlace)
            .where(WorldPlace.user_id == user_id)
            .order_by(WorldPlace.created_at, WorldPlace.id)
        )
    ).all()
    reveals = (
        await db.scalars(
            select(WorldReveal)
            .where(WorldReveal.user_id == user_id)
            .order_by(WorldReveal.learned_at, WorldReveal.id)
        )
    ).all()
    treasures = (
        await db.scalars(
            select(Treasure)
            .join(Insight, Insight.id == Treasure.insight_id)
            .where(Insight.user_id == user_id)
            .order_by(Treasure.created_at, Treasure.id)
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
            "chat_messages": await _chat_export(db, insights, messages),
            "places": places,
            "reveals": reveals,
            "treasures": treasures,
            "learner_units": units,
            "exposures": exposures,
            "photos": [
                PhotoExport(insight_id=insight.id, published=insight.photo_public_key is not None)
                for insight in insights
                if insight.photo_key is not None
            ],
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
            "sponsorships": await sponsorship_service.list_mine(db, user, everything=True),
            "learning": await export_learning(db, user.id),
        },
        from_attributes=True,
    )


async def sweep_after_deletion(photos: PhotoStore, user_id: uuid.UUID) -> None:
    """
    Empty the deleted account's photo folder once more, after the deletion is committed.

    A «تمّ» in another tab could keep a photo between the first sweep and the commit; its row
    went with the account, so only the folder still knows it. The account is gone either way:
    a store that does not answer now is logged, never reported to the person.
    """
    try:
        removed = await photos.remove_owner(user_id)
    except StorageError:
        log.warning("a deleted account's photo folder could not be swept again; the store refused")
        return
    if removed:
        log.warning("a deleted account's photo folder held %d copy(ies) kept meanwhile", removed)


async def delete_account(db: AsyncSession, user: User, *, redis: Redis, photos: PhotoStore) -> None:
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
    hour anyway). The photos kept in object storage (both copies of each) are
    deleted before the rows that know their keys; a store that cannot be reached
    stops the deletion with 503, so no photo is ever left behind without its
    account, and the person can ask again.
    """
    try:
        await photo_service.remove_all(db, photos, user.id)
    except StorageError:
        raise AppError(
            ErrorCode.STORAGE_UNAVAILABLE,
            "The account's photos could not be deleted; nothing was deleted. Try again.",
            status_code=503,
        ) from None
    scan_ids = (await db.scalars(select(Scan.id).where(Scan.user_id == user.id))).all()
    try:
        for scan_id in scan_ids:
            await buffer.drop(redis, scan_id)
    except RedisError:
        log.warning("the photos of a deleted account stay until they expire: Redis is down")
    await db.execute(delete(EvidenceExposure).where(EvidenceExposure.user_id == user.id))
    await db.execute(delete(User).where(User.id == user.id))
