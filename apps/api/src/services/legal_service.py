"""
Accepting the terms of use and the privacy policy (decision 35).

Acceptance is two consent rows, `terms` and `privacy`, each carrying the version the person
accepted and the time (the row's own `created_at`). The history is append-only, so a new
version is a new row. The current state is the latest row of each kind: unless it is granted
and of the current version, or when there is none, the account must accept again.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings
from src.errors import AppError, ErrorCode
from src.models.consent import Consent, ConsentKind

LEGAL_KINDS = (ConsentKind.TERMS, ConsentKind.PRIVACY)


def is_current(settings: Settings, terms_version: str | None, privacy_version: str | None) -> bool:
    """Whether both versions are the ones in force."""
    return terms_version == settings.terms_version and privacy_version == settings.privacy_version


def require_current(
    settings: Settings, terms_version: str | None, privacy_version: str | None
) -> None:
    """Raise a 422 `legal_acceptance_required` unless both versions are the ones in force."""
    if not is_current(settings, terms_version, privacy_version):
        raise AppError(
            ErrorCode.legal_acceptance_required,
            "Accept the current terms of use and privacy policy.",
            status_code=422,
        )


def record_acceptance(db: AsyncSession, settings: Settings, user_id: uuid.UUID) -> None:
    """Add the two rows that say the user accepted the versions in force. The caller commits."""
    db.add(
        Consent(
            user_id=user_id, kind=ConsentKind.TERMS, version=settings.terms_version, granted=True
        )
    )
    db.add(
        Consent(
            user_id=user_id,
            kind=ConsentKind.PRIVACY,
            version=settings.privacy_version,
            granted=True,
        )
    )


def record_withdrawal(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Add a `granted` false row for each text, so the account must accept again."""
    for kind in LEGAL_KINDS:
        db.add(Consent(user_id=user_id, kind=kind, version="withdrawn", granted=False))


async def acceptance_required(db: AsyncSession, settings: Settings, user_id: uuid.UUID) -> bool:
    """
    Whether the account has to accept again.

    True when, for either kind, the latest row is of another version than the one in force,
    is a withdrawal (`granted` false), or does not exist.
    """
    current = {
        ConsentKind.TERMS: settings.terms_version,
        ConsentKind.PRIVACY: settings.privacy_version,
    }
    for kind, version in current.items():
        latest = (
            await db.execute(
                select(Consent.version, Consent.granted)
                .where(Consent.user_id == user_id, Consent.kind == kind)
                .order_by(Consent.created_at.desc(), Consent.id.desc())
                .limit(1)
            )
        ).first()
        if latest is None or not latest.granted or latest.version != version:
            return True
    return False
