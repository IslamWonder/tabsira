from __future__ import annotations

import pytest
from sqlalchemy import func, select

from src.errors import AppError, ErrorCode
from src.models import AttemptKind, LoginAttempt
from src.services import rate_limit


@pytest.fixture
def settings(make_settings):
    return make_settings(
        auth_attempt_window_seconds=600, auth_max_attempts_per_ip=3, auth_max_attempts_per_email=2
    )


async def record(db, settings, kind, *, ip="ip-1", email=None, succeeded=False):
    await rate_limit.record(db, settings, kind, ip_hash=ip, email_hash=email, succeeded=succeeded)


async def test_an_ip_is_limited_after_its_failed_logins_and_told_when_to_return(
    db_session, settings, moving_clock
):
    for _ in range(3):
        await rate_limit.check(db_session, settings, AttemptKind.LOGIN, ip_hash="ip-1")
        await record(db_session, settings, AttemptKind.LOGIN)

    with pytest.raises(AppError) as caught:
        await rate_limit.check(db_session, settings, AttemptKind.LOGIN, ip_hash="ip-1")

    assert caught.value.code is ErrorCode.RATE_LIMITED
    assert caught.value.status_code == 429
    assert caught.value.headers == {"Retry-After": "600"}
    # Another address is not held to it.
    await rate_limit.check(db_session, settings, AttemptKind.LOGIN, ip_hash="ip-2")


async def test_an_email_is_limited_on_its_own_from_any_address(db_session, settings, moving_clock):
    for ip in ("ip-1", "ip-2"):
        await record(db_session, settings, AttemptKind.LOGIN, ip=ip, email="mail-1")

    with pytest.raises(AppError):
        await rate_limit.check(
            db_session, settings, AttemptKind.LOGIN, ip_hash="ip-3", email_hash="mail-1"
        )
    await rate_limit.check(
        db_session, settings, AttemptKind.LOGIN, ip_hash="ip-3", email_hash="mail-2"
    )


async def test_successful_logins_do_not_count_against_a_login_limit(
    db_session, settings, moving_clock
):
    for _ in range(10):
        await record(db_session, settings, AttemptKind.LOGIN, succeeded=True)

    await rate_limit.check(db_session, settings, AttemptKind.LOGIN, ip_hash="ip-1")


@pytest.mark.parametrize(
    "kind",
    [
        AttemptKind.SIGNUP,
        AttemptKind.GOOGLE_START,
        AttemptKind.RESEND_VERIFICATION,
        AttemptKind.PASSWORD_FORGOT,
        AttemptKind.EMAIL_TOKEN,
    ],
)
async def test_every_other_kind_counts_every_attempt_and_the_kinds_are_separate(
    db_session, settings, moving_clock, kind
):
    for _ in range(3):
        await record(db_session, settings, kind, succeeded=True)

    with pytest.raises(AppError):
        await rate_limit.check(db_session, settings, kind, ip_hash="ip-1")
    other = AttemptKind.LOGIN if kind is not AttemptKind.LOGIN else AttemptKind.SIGNUP
    await rate_limit.check(db_session, settings, other, ip_hash="ip-1")


async def test_the_window_slides_and_old_attempts_are_deleted_as_new_ones_arrive(
    db_session, settings, moving_clock
):
    for _ in range(3):
        await record(db_session, settings, AttemptKind.LOGIN)
    moving_clock.advance(seconds=601)

    await rate_limit.check(db_session, settings, AttemptKind.LOGIN, ip_hash="ip-1")
    await record(db_session, settings, AttemptKind.LOGIN, ip="ip-2")

    left = await db_session.scalar(select(func.count()).select_from(LoginAttempt))
    assert left == 1


async def test_an_attempt_holds_hashes_and_the_clock_time(db_session, settings, moving_clock):
    await record(db_session, settings, AttemptKind.SIGNUP, email="mail-1", succeeded=True)

    attempt = await db_session.scalar(select(LoginAttempt))

    assert (attempt.kind, attempt.ip_hash, attempt.email_hash, attempt.succeeded) == (
        AttemptKind.SIGNUP,
        "ip-1",
        "mail-1",
        True,
    )
    assert attempt.created_at == moving_clock.now


async def test_a_reserved_attempt_counts_at_once_and_a_refused_one_is_given_back(
    db_session, settings, moving_clock
):
    reserve = rate_limit.reserve
    first = await reserve(db_session, settings, AttemptKind.LOGIN, ip_hash="ip-1", email_hash="m")
    second = await reserve(db_session, settings, AttemptKind.LOGIN, ip_hash="ip-1", email_hash="m")

    with pytest.raises(AppError) as caught:
        await reserve(db_session, settings, AttemptKind.LOGIN, ip_hash="ip-1", email_hash="m")

    assert caught.value.status_code == 429
    ids = set((await db_session.scalars(select(LoginAttempt.id))).all())
    assert ids == {first, second}


async def test_a_settled_attempt_stops_counting(db_session, settings, moving_clock):
    for _ in range(5):
        attempt = await rate_limit.reserve(
            db_session, settings, AttemptKind.LOGIN, ip_hash="ip-1", email_hash="m"
        )
        await rate_limit.settle(db_session, attempt)

    assert await db_session.scalar(select(func.count()).select_from(LoginAttempt)) == 5
