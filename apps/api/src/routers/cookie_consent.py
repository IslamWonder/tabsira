"""
Cookie consent (decision 32): the proof that a visitor chose, and what they chose.

No sign-in is needed: the choice is made on the first visit. The id a choice is filed under is
random, made here, and kept by the browser in a first-party cookie; it is the only handle on the
record, and it is unguessable, so reading by id is how the browser asks for its own choice.
Nothing but the browser family and, when signed in, the account is kept with a choice.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from src import clock
from src.deps import DbDep, IpHashDep, OptionalUser, SettingsDep
from src.errors import AppError, ErrorCode
from src.schemas.cookie_consent import ConsentPolicyOut, CookieConsentIn, CookieConsentOut
from src.services import cookie_consent_service
from src.services.window_limiter import AddressLimits, limits_of, too_many_requests

router = APIRouter(prefix="/consent", tags=["consent"])

# A choice is a few dozen bytes; the cap is for what a caller might add to it.
MAX_BODY_BYTES = 4 * 1024
# Each choice is a row, so the route is limited like the other open ones: per address, and
# over all addresses, in each worker.
ADDRESS_LIMIT = 30
GLOBAL_LIMIT = 600
WINDOW_SECONDS = 300


def get_limits(request: Request) -> AddressLimits:
    """Return the application's limits for this route, built on first use."""
    return limits_of(
        request,
        "consent_limits",
        lambda: AddressLimits(ADDRESS_LIMIT, GLOBAL_LIMIT, WINDOW_SECONDS),
    )


def enforce_limits(
    limits: Annotated[AddressLimits, Depends(get_limits)], ip_hash: IpHashDep
) -> None:
    """Answer 429 when this address, or this worker as a whole, has recorded too many choices."""
    retry_after = limits.hit(ip_hash)
    if retry_after is not None:
        raise too_many_requests(retry_after, "Too many choices recorded. Try again later.")


# Declared before the id route: "policy" must not be read as an id.
@router.get("/policy", summary="The categories to choose between and the re-ask interval")
async def get_policy(settings: SettingsDep) -> ConsentPolicyOut:
    """
    Return the current policy.

    The policy is its version, each category with its Arabic title and description, and the
    number of days after which a choice lapses and the visitor is asked again.
    """
    return cookie_consent_service.policy(settings)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_limits)],
    summary="Record a cookie choice",
)
async def post_consent(
    body: CookieConsentIn,
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    user: OptionalUser,
) -> CookieConsentOut:
    """
    Append the choice and return the consent id with what is in force.

    The first call has no `consent_id`; keep the one returned in a first-party cookie and send
    it with every later choice, so they are one history. Choosing again is a new record, never
    an edit. The user agent is reduced to its browser family and no address is kept.
    """
    row = await cookie_consent_service.record_choice(
        db,
        settings,
        consent_id=body.consent_id,
        policy_version=body.policy_version,
        analytics=body.analytics,
        behaviour=body.behaviour,
        user_agent=request.headers.get("user-agent"),
        user=user,
    )
    await db.commit()
    return cookie_consent_service.in_force(row, settings, clock.utcnow())


@router.get("/{consent_id}", summary="The choice in force for a consent id")
async def get_consent(consent_id: uuid.UUID, db: DbDep, settings: SettingsDep) -> CookieConsentOut:
    """
    Return what the id's latest choice allows now.

    While the choice is current its categories are the ones chosen; once the policy changed or
    the re-ask interval passed, `reask` is true and only the necessary category is on. An id the
    server never issued is a 404.
    """
    row = await cookie_consent_service.latest(db, consent_id)
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, "No choice is recorded for this id.", status_code=404)
    return cookie_consent_service.in_force(row, settings, clock.utcnow())
