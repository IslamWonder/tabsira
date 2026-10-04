"""`rate_limit.reserve_budgets`: count before the work is done, over a window of its own."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from src import security
from src.errors import AppError, ErrorCode
from src.models import AttemptKind, LoginAttempt
from src.services import rate_limit

LIMITS = {"per_ip": 2, "per_email": 1, "overall": 3, "window_seconds": 3600}


async def reserve(db, settings, ip="ip-1", email="mail-1"):
    await rate_limit.reserve_budgets(
        db, settings, AttemptKind.SUPPORT, ip_hash=ip, email_hash=email, **LIMITS
    )


async def test_a_reservation_is_counted_at_once(db_session, make_settings, moving_clock):
    await reserve(db_session, make_settings())

    count = await db_session.scalar(select(func.count()).select_from(LoginAttempt))
    assert count == 1


@pytest.mark.parametrize(
    ("second", "reason"),
    [
        ({"ip": "ip-2"}, "address"),  # same e-mail address from another IP
    ],
)
async def test_one_address_is_limited_on_its_own_from_any_ip(
    db_session, make_settings, moving_clock, second, reason
):
    settings = make_settings()
    await reserve(db_session, settings)

    with pytest.raises(AppError) as caught:
        await reserve(db_session, settings, **second)

    assert caught.value.code is ErrorCode.RATE_LIMITED
    assert caught.value.headers == {"Retry-After": "3600"}


async def test_one_ip_is_limited_whatever_the_address(db_session, make_settings, moving_clock):
    settings = make_settings()
    await reserve(db_session, settings, email="a")
    await reserve(db_session, settings, email="b")

    with pytest.raises(AppError):
        await reserve(db_session, settings, email="c")


async def test_the_overall_ceiling_stops_a_flood_of_fresh_ip_and_addresses(
    db_session, make_settings, moving_clock
):
    settings = make_settings()
    for number in range(3):
        await reserve(db_session, settings, ip=f"ip-{number}", email=f"mail-{number}")

    with pytest.raises(AppError):
        await reserve(db_session, settings, ip="ip-9", email="mail-9")


async def test_the_window_is_the_routes_own_and_old_rows_are_purged_by_it(
    db_session, make_settings, moving_clock
):
    # The sign-in window is 15 minutes; a support row must outlive it and then go.
    settings = make_settings()
    await reserve(db_session, settings)
    moving_clock.advance(minutes=30)
    with pytest.raises(AppError):
        await reserve(db_session, settings)

    moving_clock.advance(minutes=31)
    await reserve(db_session, settings)

    count = await db_session.scalar(select(func.count()).select_from(LoginAttempt))
    assert count == 1


async def test_a_sign_in_record_does_not_purge_support_rows_inside_their_window(
    db_session, make_settings, moving_clock
):
    settings = make_settings()
    await reserve(db_session, settings)
    moving_clock.advance(minutes=30)

    await rate_limit.record(
        db_session, settings, AttemptKind.LOGIN, ip_hash="x", email_hash=None, succeeded=False
    )

    kinds = set((await db_session.scalars(select(LoginAttempt.kind))).all())
    assert kinds == {AttemptKind.SUPPORT, AttemptKind.LOGIN}


def test_an_ipv6_address_can_be_grouped_by_its_48():
    one = security.normalize_client_ip("2001:db8:1:1::5", ipv6_prefix=48)
    other = security.normalize_client_ip("2001:db8:1:ffff::9", ipv6_prefix=48)

    assert one == other == "2001:db8:1::/48"
    assert security.normalize_client_ip("2001:db8:1:1::5") == "2001:db8:1:1::/64"
