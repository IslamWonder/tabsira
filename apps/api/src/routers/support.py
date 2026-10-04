"""
The support form (decision 34): it emails SUPPORT_EMAIL and keeps no message.

No sign-in is needed. The message goes out at once over SMTP with the visitor's address as
Reply-To; if it cannot, the answer is 503 `mail_unavailable`, so the page never claims a
message was sent that was not. Neither the body nor the address is logged or kept (only keyed
hashes of the address and the IP, for an hour, to limit the route), and the
mail carries no IP address or browser data.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings
from src.deps import DbDep, SettingsDep, UngatedOptionalUser
from src.errors import AppError, ErrorCode
from src.models.login_attempt import AttemptKind
from src.models.user import User
from src.schemas.auth import StatusOut
from src.schemas.support import SupportIn
from src.services import auth_service, email_service, rate_limit

router = APIRouter(prefix="/support", tags=["support"])

# A message is at most 4000 characters; the rest is the JSON around it and some slack for
# characters that take several bytes.
MAX_BODY_BYTES = 8 * 1024
# A whole site (a /48) is one sender for the limit.
SUPPORT_IPV6_PREFIX = 48


def _matches_account(user: User | None, address: str) -> bool | None:
    """None for a guest; else whether the typed address is the account's own, verified one."""
    if user is None:
        return None
    return user.email_verified_at is not None and (
        auth_service.normalize_email(address) == user.email
    )


async def _reserve(db: AsyncSession, settings: Settings, request: Request, address: str) -> None:
    """Count this message against its IP (IPv6 by /48), its reply-to address and everyone."""
    host = request.client.host if request.client else None
    await rate_limit.reserve_budgets(
        db,
        settings,
        AttemptKind.SUPPORT,
        ip_hash=auth_service.hash_ip(settings, host, ipv6_prefix=SUPPORT_IPV6_PREFIX),
        email_hash=auth_service.hash_email(settings, address),
        per_ip=settings.support_max_per_ip_per_hour,
        per_email=settings.support_max_per_address_per_hour,
        overall=settings.support_max_per_hour,
        window_seconds=rate_limit.SUPPORT_WINDOW_SECONDS,
    )
    # Committed before the mail goes: a failing mail server must not be a way round the limit.
    await db.commit()


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send a message to support",
)
async def send_support(
    body: SupportIn,
    request: Request,
    db: DbDep,
    user: UngatedOptionalUser,
    settings: SettingsDep,
) -> StatusOut:
    """
    Email the message to the support address, replies going to the visitor.

    A filled `website` field is a bot: it gets the same 202 and nothing is sent. The account
    id is added to the mail when a valid session cookie is present. Answers 503
    `mail_unavailable` when mail is not configured or the send fails. The attempt is counted
    (keyed hashes in PostgreSQL, shared by every worker) before the mail is sent.
    """
    if body.website:
        return StatusOut(status="accepted")
    await _reserve(db, settings, request, body.email)
    sent = await email_service.send_support_message(
        settings,
        reply_to=body.email,
        topic=body.topic.value,
        name=body.name,
        text=body.message,
        account_id=str(user.id) if user is not None else None,
        account_match=_matches_account(user, body.email),
    )
    if not sent:
        raise AppError(
            ErrorCode.mail_unavailable,
            "The message could not be sent. Try again later.",
            status_code=503,
        )
    return StatusOut(status="accepted")
