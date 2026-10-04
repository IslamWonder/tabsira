"""Everything an account owns: exporting it, and deleting it."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock
from src.models.consent import Consent
from src.models.session import Session
from src.models.user import OAuthAccount, User
from src.schemas.account import AccountExport
from src.schemas.cookie_consent import CookieConsentExport
from src.schemas.profile import ConsentOut, ProfileOut
from src.services import cookie_consent_service, profile_service


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
        },
        from_attributes=True,
    )


async def delete_account(db: AsyncSession, user: User) -> None:
    """
    Delete the user and, by ON DELETE CASCADE, everything that references them.

    Sessions, linked identities, the profile, the consent history, the cookie
    choices made while signed in and the mailed tokens all go with the row. The
    cookie-consent table is append-only, and its guard lets exactly this cascade
    through. Anything a later feature stores outside the database (photos in
    object storage) must be removed here before the row.
    """
    await db.execute(delete(User).where(User.id == user.id))
