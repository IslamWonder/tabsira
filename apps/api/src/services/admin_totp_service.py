"""
The second factor of the admin area: a time-based one-time password (RFC 6238).

Three things are stored, each the way its job needs:

- The shared secret, encrypted with Fernet under ADMIN_TOTP_ENCRYPTION_KEY. It has to
  be recoverable (the server recomputes the code), so it is encrypted, not hashed; a
  copy of the table without the key is useless. Several keys may be configured, so a key
  is rotated by putting the new one first.
- The recovery codes, as keyed hashes (HMAC-SHA256 under the server's hash key). Each
  works once and is removed when it is spent.
- The step of the last accepted code. A code is valid for its own 30-second step and one
  either side, which without a guard lets one code open three sign-ins; refusing any step
  at or below the last one makes a code worth exactly one.

Every comparison is constant time. The time comes from `src.clock`, so a test can fix it.
"""

from __future__ import annotations

import hmac
import logging
import re
import secrets
import uuid

import pyotp
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import delete, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock, security
from src.config import Settings
from src.models.admin_access import AdminTotp
from src.models.user import User

log = logging.getLogger("tabsira.admin.totp")

ISSUER = "TABSIRA admin"
# RFC 6238 defaults, which every authenticator app assumes.
STEP_SECONDS = 30
# One step either side, to survive a phone clock that drifted.
DRIFT_STEPS = 1
RECOVERY_CODE_COUNT = 10
RECOVERY_PURPOSE = "admin-recovery-code"
# ASCII digits only: `\d` would also accept the Arabic-Indic ones, which no app produces.
_CODE = re.compile(r"[0-9]{6}")


def _fernet(settings: Settings) -> MultiFernet:
    return MultiFernet([Fernet(key) for key in settings.admin_totp_keys])


def encrypt_secret(settings: Settings, secret: str) -> str:
    """Return the secret as the token that is stored."""
    return _fernet(settings).encrypt(secret.encode()).decode()


def decrypt_secret(settings: Settings, token: str) -> str | None:
    """
    Return the secret a stored token holds, or None when no configured key opens it.

    None means the keys were changed without keeping the old one: the second factor
    cannot be verified, so it fails closed, and the log says why.
    """
    try:
        return _fernet(settings).decrypt(token.encode()).decode()
    except InvalidToken:
        log.exception(
            "An admin second-factor secret cannot be decrypted: check ADMIN_TOTP_ENCRYPTION_KEY"
        )
        return None


def hash_recovery_code(settings: Settings, code: str) -> str:
    """Return the keyed hash a recovery code is stored as, whatever its case or dashes."""
    normalized = re.sub(r"[\s-]", "", code).lower()
    return security.keyed_hash(settings.hash_key, RECOVERY_PURPOSE, normalized)


def new_recovery_codes() -> list[str]:
    """Draw the recovery codes: sixteen hex digits, grouped for reading off a printout."""
    return ["-".join(secrets.token_hex(2) for _ in range(4)) for _ in range(RECOVERY_CODE_COUNT)]


def provisioning_uri(user: User, secret: str) -> str:
    """Return the `otpauth://` address an authenticator app takes."""
    return pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=ISSUER)


def readable(secret: str) -> str:
    """Return the secret in groups of four, for typing into an authenticator by hand."""
    return " ".join(secret[index : index + 4] for index in range(0, len(secret), 4))


def is_enabled(row: AdminTotp | None) -> bool:
    """Whether the admin has finished enrolling, so the code is required at sign-in."""
    return row is not None and row.enabled_at is not None


async def get(db: AsyncSession, user_id: uuid.UUID) -> AdminTotp | None:
    """Return the second factor of an admin, enrolled or only started."""
    return await db.get(AdminTotp, user_id, populate_existing=True)


def _matching_step(secret: str, code: str) -> int | None:
    """Return the step `code` is the code of, within the drift window, or None."""
    if not _CODE.fullmatch(code):
        return None
    totp = pyotp.TOTP(secret)
    now = int(clock.utcnow().timestamp())
    for offset in range(-DRIFT_STEPS, DRIFT_STEPS + 1):
        if hmac.compare_digest(totp.at(now, offset), code):
            return now // STEP_SECONDS + offset
    return None


async def start_enrollment(db: AsyncSession, settings: Settings, user: User) -> str:
    """
    Mint a fresh secret for an admin who is not enrolled and return it; it is not on yet.

    Starting again before confirming replaces the secret. An enrolled admin must switch
    the second factor off before starting over, which the caller checks.
    """
    secret = pyotp.random_base32()
    await db.execute(delete(AdminTotp).where(AdminTotp.user_id == user.id))
    db.add(AdminTotp(user_id=user.id, secret_encrypted=encrypt_secret(settings, secret)))
    await db.flush()
    return secret


async def confirm_enrollment(
    db: AsyncSession, settings: Settings, user: User, code: str
) -> list[str] | None:
    """
    Switch the second factor on once the admin proves their app produces the code.

    Returns the recovery codes, in clear for this one answer, or None when there is no
    pending enrolment or the code is wrong. Enabling on a scanned secret alone would
    lock out whoever's app did not take it.
    """
    row = await get(db, user.id)
    if row is None or row.enabled_at is not None:
        return None
    secret = decrypt_secret(settings, row.secret_encrypted)
    step = None if secret is None else _matching_step(secret, code)
    if step is None:
        return None
    codes = new_recovery_codes()
    row.recovery_hashes = [hash_recovery_code(settings, entry) for entry in codes]
    row.enabled_at = clock.utcnow()
    row.last_used_step = step
    await db.flush()
    return codes


async def verify(db: AsyncSession, settings: Settings, user: User, code: str) -> bool:
    """
    Check an authenticator code or a recovery code of an enrolled admin and spend it.

    The authenticator code is tried first, so a valid one never burns a recovery code.
    """
    row = await get(db, user.id)
    if not is_enabled(row) or row is None:
        return False
    secret = decrypt_secret(settings, row.secret_encrypted)
    step = None if secret is None else _matching_step(secret, code)
    if step is not None:
        return await _spend_step(db, user.id, step)
    return await _spend_recovery_code(db, settings, user.id, code)


async def _spend_step(db: AsyncSession, user_id: uuid.UUID, step: int) -> bool:
    """Record the step as used unless it, or a later one, was used already; atomic."""
    result = await db.execute(
        update(AdminTotp)
        .where(
            AdminTotp.user_id == user_id,
            (AdminTotp.last_used_step.is_(None)) | (AdminTotp.last_used_step < step),
        )
        .values(last_used_step=step)
        .returning(AdminTotp.user_id)
    )
    return result.first() is not None


async def _spend_recovery_code(
    db: AsyncSession, settings: Settings, user_id: uuid.UUID, code: str
) -> bool:
    """Remove the recovery code from the list if it is there; atomic, so it works once."""
    hashed = hash_recovery_code(settings, code)
    result = await db.execute(
        update(AdminTotp)
        .where(AdminTotp.user_id == user_id, AdminTotp.recovery_hashes.contains([hashed]))
        .values(recovery_hashes=func.array_remove(AdminTotp.recovery_hashes, hashed))
        .returning(AdminTotp.user_id)
    )
    return result.first() is not None


async def disable(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Remove the second factor of an admin, secret and codes alike; say if there was one."""
    result = await db.execute(
        delete(AdminTotp).where(AdminTotp.user_id == user_id).returning(AdminTotp.user_id)
    )
    return result.first() is not None
