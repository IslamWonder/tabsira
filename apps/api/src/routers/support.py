"""
The support form (decision 34): it emails SUPPORT_EMAIL and stores nothing.

No sign-in is needed. The message goes out at once over SMTP with the visitor's address as
Reply-To; if it cannot, the answer is 503 `mail_unavailable`, so the page never claims a
message was sent that was not. Neither the body nor the address is logged or kept, and the
mail carries no IP address or browser data.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from src.deps import IpHashDep, SettingsDep, UngatedOptionalUser
from src.errors import AppError, ErrorCode
from src.schemas.auth import StatusOut
from src.schemas.support import SupportIn
from src.services import email_service
from src.services.window_limiter import AddressLimits, limits_of, too_many_requests

router = APIRouter(prefix="/support", tags=["support"])

# A message is at most 4000 characters; the rest is the JSON around it and some slack for
# characters that take several bytes.
MAX_BODY_BYTES = 8 * 1024
WINDOW_SECONDS = 3600


def get_limits(request: Request, settings: SettingsDep) -> AddressLimits:
    """Return the application's limits for this route, built on first use."""
    return limits_of(
        request,
        "support_limits",
        lambda: AddressLimits(
            settings.support_max_per_address_per_hour,
            settings.support_max_per_hour,
            WINDOW_SECONDS,
        ),
    )


def enforce_limits(
    limits: Annotated[AddressLimits, Depends(get_limits)], ip_hash: IpHashDep
) -> None:
    """Answer 429 when this address, or this worker as a whole, has sent too many messages."""
    retry_after = limits.hit(ip_hash)
    if retry_after is not None:
        raise too_many_requests(retry_after, "Too many messages. Try again later.")


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_limits)],
    summary="Send a message to support",
)
async def send_support(
    body: SupportIn, user: UngatedOptionalUser, settings: SettingsDep
) -> StatusOut:
    """
    Email the message to the support address, replies going to the visitor.

    A filled `website` field is a bot: it gets the same 202 and nothing is sent. The account
    id is added to the mail when a valid session cookie is present. Answers 503
    `mail_unavailable` when mail is not configured or the send fails.
    """
    if body.website:
        return StatusOut(status="accepted")
    sent = await email_service.send_support_message(
        settings,
        reply_to=body.email,
        topic=body.topic.value,
        name=body.name,
        text=body.message,
        account_id=str(user.id) if user is not None else None,
    )
    if not sent:
        raise AppError(
            ErrorCode.mail_unavailable,
            "The message could not be sent. Try again later.",
            status_code=503,
        )
    return StatusOut(status="accepted")
