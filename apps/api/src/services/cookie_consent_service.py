"""
Cookie consent: recording what a visitor chose, and working out what is in force.

A choice is a row of `cookie_consents`, never edited. The choice in force for a consent id is
its latest row, as long as it was made for the current policy version and is younger than
`CONSENT_REASK_DAYS`; after that nothing but the necessary category may run until the visitor
chooses again.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock
from src.config import Settings
from src.messages import messages_for
from src.models.cookie_consent import CookieConsent
from src.models.user import User
from src.schemas.cookie_consent import (
    ConsentCategories,
    ConsentCategoryOut,
    ConsentPolicyOut,
    CookieConsentOut,
)
from src.user_agent import user_agent_family


def categories(settings: Settings) -> list[ConsentCategoryOut]:
    """Return the categories in the order a visitor sees them; the necessary one is not optional."""
    text = messages_for(settings=settings)
    return [
        ConsentCategoryOut(
            key="necessary",
            required=True,
            title=text.consent_necessary_title,
            description=text.consent_necessary_description,
        ),
        ConsentCategoryOut(
            key="analytics",
            required=False,
            title=text.consent_analytics_title,
            description=text.consent_analytics_description,
        ),
        ConsentCategoryOut(
            key="behaviour",
            required=False,
            title=text.consent_behaviour_title,
            description=text.consent_behaviour_description,
        ),
    ]


def policy(settings: Settings) -> ConsentPolicyOut:
    """Return the current policy: its version, the categories and when a choice lapses."""
    return ConsentPolicyOut(
        policy_version=settings.cookie_policy_version,
        reask_days=settings.consent_reask_days,
        categories=categories(settings),
    )


async def latest(db: AsyncSession, consent_id: uuid.UUID) -> CookieConsent | None:
    """Return the choice in force for an id as last recorded, or None for an id never seen."""
    return await db.scalar(
        select(CookieConsent)
        .where(CookieConsent.consent_id == consent_id)
        .order_by(CookieConsent.created_at.desc(), CookieConsent.id.desc())
        .limit(1)
    )


async def _is_known(db: AsyncSession, consent_id: uuid.UUID) -> bool:
    found = await db.scalar(select(exists().where(CookieConsent.consent_id == consent_id)))
    return bool(found)


async def record_choice(
    db: AsyncSession,
    settings: Settings,
    *,
    consent_id: uuid.UUID | None,
    policy_version: str | None,
    analytics: bool,
    behaviour: bool,
    user_agent: str | None,
    user: User | None,
) -> CookieConsent:
    """
    Append a choice and return it. It only flushes: the caller commits.

    The id is the browser's own when the server knows it, and a new random one otherwise: the
    server alone makes ids, so a visitor cannot pick one that is not theirs to pick. Nothing
    of the request is kept but the browser family and, when signed in, the account.
    """
    known = consent_id is not None and await _is_known(db, consent_id)
    row = CookieConsent(
        consent_id=consent_id if known and consent_id is not None else uuid.uuid4(),
        policy_version=policy_version or settings.cookie_policy_version,
        necessary=True,
        analytics=analytics,
        behaviour=behaviour,
        user_agent_family=user_agent_family(user_agent),
        user_id=user.id if user is not None else None,
        created_at=clock.utcnow(),
    )
    db.add(row)
    await db.flush()
    return row


def in_force(row: CookieConsent, settings: Settings, now: datetime) -> CookieConsentOut:
    """Work out what the recorded choice allows at `now`."""
    expires_at = row.created_at + settings.consent_reask
    lapsed = row.policy_version != settings.cookie_policy_version or now >= expires_at
    return CookieConsentOut(
        consent_id=row.consent_id,
        policy_version=row.policy_version,
        decided_at=row.created_at,
        expires_at=expires_at,
        reask=lapsed,
        categories=ConsentCategories(
            analytics=row.analytics and not lapsed, behaviour=row.behaviour and not lapsed
        ),
    )


async def choices_of(db: AsyncSession, user: User) -> list[CookieConsent]:
    """Return every choice made while `user` was signed in, oldest first."""
    rows = await db.scalars(
        select(CookieConsent)
        .where(CookieConsent.user_id == user.id)
        .order_by(CookieConsent.created_at, CookieConsent.id)
    )
    return list(rows)
