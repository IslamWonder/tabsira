"""E-mail verification and password reset: links mailed to an address, spent once."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, Request, status

from src import clock, security
from src.deps import DbDep, HumanDep, IpHashDep, SettingsDep
from src.errors import AppError, ErrorCode
from src.models.email_token import TokenPurpose
from src.models.login_attempt import AttemptKind
from src.schemas.auth import EmailIn, ResetPasswordIn, StatusOut, VerifyEmailIn
from src.services import (
    auth_service,
    email_service,
    email_token_service,
    rate_limit,
    session_service,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _invalid_link() -> AppError:
    # One answer for every way a link can be bad, so it says nothing about which.
    return AppError(ErrorCode.INVALID_TOKEN, "The link is invalid or has expired.", status_code=400)


@router.post("/verify-email", summary="Confirm an e-mail address with the mailed link's token")
async def verify_email(
    body: VerifyEmailIn, db: DbDep, settings: SettingsDep, ip_hash: IpHashDep
) -> StatusOut:
    """
    Mark the address verified. The token works once; any bad token answers the same 400.

    The caller needs no session: whoever holds the token read the mail.
    """
    await rate_limit.check(db, settings, AttemptKind.EMAIL_TOKEN, ip_hash=ip_hash)
    user = await email_token_service.redeem(db, body.token, TokenPurpose.VERIFY_EMAIL)
    await rate_limit.record(
        db, settings, AttemptKind.EMAIL_TOKEN, ip_hash=ip_hash, succeeded=user is not None
    )
    if user is None:
        await db.commit()
        raise _invalid_link()
    if user.email_verified_at is None:
        user.email_verified_at = clock.utcnow()
    await db.commit()
    return StatusOut(status="ok")


@router.post(
    "/resend-verification",
    dependencies=[HumanDep],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Mail the verification link again",
)
async def resend_verification(
    body: EmailIn,
    background: BackgroundTasks,
    db: DbDep,
    settings: SettingsDep,
    ip_hash: IpHashDep,
) -> StatusOut:
    """
    Answer 202 whether or not the address has an unverified account.

    Rate limited per IP and per address. A new link cancels the earlier one.
    """
    email_hash = auth_service.hash_email(settings, body.email)
    kind = AttemptKind.RESEND_VERIFICATION
    await rate_limit.check(db, settings, kind, ip_hash=ip_hash, email_hash=email_hash)
    await rate_limit.record(
        db, settings, kind, ip_hash=ip_hash, email_hash=email_hash, succeeded=True
    )
    user = await auth_service.find_by_email(db, body.email)
    if user is not None and auth_service.can_sign_in(user) and user.email_verified_at is None:
        token = await email_token_service.issue(db, settings, user, TokenPurpose.VERIFY_EMAIL)
        background.add_task(
            email_service.send_email_verification,
            settings,
            email=user.email,
            name=user.display_name,
            token=token,
        )
    await db.commit()
    return StatusOut(status="accepted")


@router.post(
    "/forgot-password",
    dependencies=[HumanDep],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Mail a password reset link",
)
async def forgot_password(
    body: EmailIn,
    background: BackgroundTasks,
    db: DbDep,
    settings: SettingsDep,
    ip_hash: IpHashDep,
) -> StatusOut:
    """
    Answer 202 whether or not the address has an account.

    Rate limited per IP and per address. A new link cancels the earlier one. The
    mail is sent after the answer, so the time it takes says nothing either.
    """
    email_hash = auth_service.hash_email(settings, body.email)
    kind = AttemptKind.PASSWORD_FORGOT
    await rate_limit.check(db, settings, kind, ip_hash=ip_hash, email_hash=email_hash)
    await rate_limit.record(
        db, settings, kind, ip_hash=ip_hash, email_hash=email_hash, succeeded=True
    )
    user = await auth_service.find_by_email(db, body.email)
    if user is not None and auth_service.can_sign_in(user):
        token = await email_token_service.issue(db, settings, user, TokenPurpose.PASSWORD_RESET)
        background.add_task(
            email_service.send_password_reset,
            settings,
            email=user.email,
            name=user.display_name,
            token=token,
        )
    await db.commit()
    return StatusOut(status="accepted")


@router.post("/reset-password", summary="Choose a new password with the mailed link's token")
async def reset_password(
    body: ResetPasswordIn,
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    ip_hash: IpHashDep,
) -> StatusOut:
    """
    Set the new password and end every other session of the account.

    The token works once. Following it also proves the address, so it is marked
    verified. The caller is not signed in by it: they sign in with the new password.
    """
    await rate_limit.check(db, settings, AttemptKind.EMAIL_TOKEN, ip_hash=ip_hash)
    user = await email_token_service.redeem(db, body.token, TokenPurpose.PASSWORD_RESET)
    await rate_limit.record(
        db, settings, AttemptKind.EMAIL_TOKEN, ip_hash=ip_hash, succeeded=user is not None
    )
    if user is None:
        await db.commit()
        raise _invalid_link()
    user.password_hash = await asyncio.to_thread(
        security.hash_password, body.password, settings.password_bcrypt_rounds
    )
    if user.email_verified_at is None:
        user.email_verified_at = clock.utcnow()
    await email_token_service.cancel_unused(db, user.id, TokenPurpose.PASSWORD_RESET)
    await session_service.revoke_every_session(
        db, user.id, keep_token=session_service.cookie_token(request, settings)
    )
    await db.commit()
    return StatusOut(status="ok")
