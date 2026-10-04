"""
Accounts: signing up, signing in with a password, and linking Google.

Rules that hold throughout:
- Addresses are stored lower-cased and found by `lower(email)`.
- A wrong address and a wrong password give the same answer, in the same time.
- Sign-in and sign-up are rate limited before any password is hashed or checked.
- An attempt that gets refused is recorded and committed before it is refused:
  a rolled-back transaction would take the count with it.
- An unverified address may sign in. It may not publish anything public
  (`deps.verified_user`); verification is a flag, `email_verified_at`.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock, security
from src.config import Settings
from src.errors import AppError, ErrorCode
from src.models.login_attempt import AttemptKind
from src.models.user import GOOGLE, OAuthAccount, User
from src.schemas.auth import DISPLAY_NAME_MAX, UserOut
from src.services import legal_service, profile_service, rate_limit, session_service
from src.services.google_oidc import GoogleIdentity

EMAIL_HASH_PURPOSE = "email"
IP_HASH_PURPOSE = "ip"
# What the web app is told when a Google sign-in is refused (`/login?error=<code>`).
WEB_ACCOUNT_DISABLED = "account_disabled"
WEB_GOOGLE_FAILED = "google_failed"


def normalize_email(email: str) -> str:
    """Return an address the way it is stored: trimmed and lower-cased."""
    return email.strip().lower()


def hash_email(settings: Settings, email: str) -> str:
    """Return the keyed hash a rate limit counts an address by."""
    return security.keyed_hash(settings.hash_key, EMAIL_HASH_PURPOSE, normalize_email(email))


def hash_ip(settings: Settings, host: str | None) -> str:
    """Return the keyed hash of a client address, after cutting IPv6 to its /64."""
    return security.keyed_hash(
        settings.hash_key, IP_HASH_PURPOSE, security.normalize_client_ip(host)
    )


async def find_by_email(db: AsyncSession, email: str) -> User | None:
    """Return the account of an address, whatever the case it was typed in."""
    return await db.scalar(
        select(User).where(func.lower(User.email) == func.lower(normalize_email(email)))
    )


async def describe(db: AsyncSession, settings: Settings, user: User) -> UserOut:
    """Build the account view the signed-in user gets of themselves."""
    providers = (
        await db.scalars(select(OAuthAccount.provider).where(OAuthAccount.user_id == user.id))
    ).all()
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        email_verified=user.email_verified_at is not None,
        has_password=user.password_hash is not None,
        providers=sorted(providers),
        created_at=user.created_at,
        legal_acceptance_required=await legal_service.acceptance_required(db, settings, user.id),
    )


def can_sign_in(user: User) -> bool:
    """Whether the account may start a session."""
    return user.is_active and user.deleted_at is None


async def signup(
    db: AsyncSession,
    settings: Settings,
    *,
    email: str,
    password: str,
    display_name: str,
    ip_hash: str,
    accepted_terms_version: str,
    accepted_privacy_version: str,
) -> User:
    """
    Create an account with an e-mail address and a password, and its empty profile.

    The versions of the terms and the privacy policy the person accepted must be the
    current ones; that is checked first, so a sign-up that did not accept creates and
    counts nothing. The acceptance is recorded in the same transaction as the account.
    """
    legal_service.require_current(settings, accepted_terms_version, accepted_privacy_version)
    normalized = normalize_email(email)
    email_hash = hash_email(settings, normalized)
    # Every sign-up counts, so the attempt is taken before the slow hash and never settled.
    await rate_limit.reserve(
        db, settings, AttemptKind.SIGNUP, ip_hash=ip_hash, email_hash=email_hash
    )
    taken = AppError(
        ErrorCode.EMAIL_TAKEN, "An account already uses this e-mail address.", status_code=409
    )
    if await find_by_email(db, normalized) is not None:
        raise taken
    password_hash = await asyncio.to_thread(
        security.hash_password, password, settings.password_bcrypt_rounds
    )
    user = User(email=normalized, password_hash=password_hash, display_name=display_name)
    try:
        # A savepoint: two sign-ups racing for one address both pass the check
        # above, and the unique index refuses the second one here.
        async with db.begin_nested():
            db.add(user)
            await db.flush()
    except IntegrityError:
        raise taken from None
    await profile_service.ensure_profile(db, user.id)
    legal_service.record_acceptance(db, settings, user.id)
    return user


async def login(
    db: AsyncSession, settings: Settings, *, email: str, password: str, ip_hash: str
) -> User:
    """
    Check an address and a password and return the account.

    The attempt is taken before the password is checked (`rate_limit.reserve`), so parallel
    requests cannot all slip under the limit while bcrypt runs; a refusal then has nothing
    left to record, and only a success changes the attempt.

    The password is checked even when no account has the address, against a
    decoy, so the answer and its timing do not say whether the address exists.
    """
    email_hash = hash_email(settings, email)
    attempt = await rate_limit.reserve(
        db, settings, AttemptKind.LOGIN, ip_hash=ip_hash, email_hash=email_hash
    )
    user = await find_by_email(db, email)
    correct = await asyncio.to_thread(
        security.verify_password,
        password,
        user.password_hash if user else None,
        settings.password_bcrypt_rounds,
    )
    if user is None or not correct:
        raise AppError(
            ErrorCode.INVALID_CREDENTIALS,
            "The e-mail address or the password is wrong.",
            status_code=401,
        )
    if not can_sign_in(user):
        # Only someone who knows the password learns this.
        raise AppError(ErrorCode.ACCOUNT_DISABLED, "This account is disabled.", status_code=403)
    await rate_limit.settle(db, attempt)
    return user


class SignInRefusedError(Exception):
    """A Google sign-in cannot go on; `code` is the reason the web app is told."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _google_display_name(identity: GoogleIdentity, email: str) -> str:
    name = " ".join((identity.name or "").split())[:DISPLAY_NAME_MAX]
    return name or email.split("@", maxsplit=1)[0][:DISPLAY_NAME_MAX]


async def sign_in_with_google(
    db: AsyncSession,
    settings: Settings,
    identity: GoogleIdentity,
    *,
    accepted_terms_version: str | None = None,
    accepted_privacy_version: str | None = None,
) -> User:
    """
    Return the account of a verified Google identity, linking or creating it.

    Order: the identity already linked; else the account that has the same
    (Google-verified) address; else a new account. When Google's verified address
    meets a password account whose address nobody ever proved, the password is
    removed and the account's sessions are ended: whoever registered that address
    first may have been a stranger who then waits for the owner to arrive
    (account pre-hijacking). The owner keeps the account, through Google.

    When the account is new and the versions ticked before leaving for Google are the
    current ones, the acceptance is recorded with it. An existing account is untouched:
    it is asked through `legal_acceptance_required` if it has not accepted.
    """
    linked = await db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.provider == GOOGLE, OAuthAccount.subject == identity.subject
        )
    )
    if linked is not None:
        user = await db.get(User, linked.user_id)
    else:
        user, created = await _link_or_create(db, identity)
        if created and legal_service.is_current(
            settings, accepted_terms_version, accepted_privacy_version
        ):
            legal_service.record_acceptance(db, settings, user.id)
    if user is None or not can_sign_in(user):
        raise SignInRefusedError(WEB_ACCOUNT_DISABLED)
    return user


async def _link_or_create(db: AsyncSession, identity: GoogleIdentity) -> tuple[User, bool]:
    email = normalize_email(identity.email)
    now: datetime = clock.utcnow()
    user = await find_by_email(db, email)
    created = user is None
    if user is None:
        user = User(
            email=email,
            password_hash=None,
            display_name=_google_display_name(identity, email),
            email_verified_at=now,
        )
    elif not can_sign_in(user):
        # Refused before anything is linked to a disabled account.
        raise SignInRefusedError(WEB_ACCOUNT_DISABLED)
    elif user.email_verified_at is None:
        if user.password_hash is not None:
            user.password_hash = None
            await session_service.revoke_every_session(db, user.id)
            # What the stranger accepted is not the owner's acceptance.
            legal_service.record_withdrawal(db, user.id)
        user.email_verified_at = now
    try:
        async with db.begin_nested():
            db.add(user)
            await db.flush()
            db.add(OAuthAccount(user_id=user.id, provider=GOOGLE, subject=identity.subject))
            await db.flush()
    except IntegrityError:
        # Two callbacks for one new person raced; the loser is sent back to try again.
        raise SignInRefusedError(WEB_GOOGLE_FAILED) from None
    await profile_service.ensure_profile(db, user.id)
    return user, created
