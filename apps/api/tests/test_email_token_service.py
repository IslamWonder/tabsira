from __future__ import annotations

import pytest
from sqlalchemy import func, select

from src import security
from src.models import EmailToken, TokenPurpose
from src.services import email_token_service

VERIFY, RESET = TokenPurpose.VERIFY_EMAIL, TokenPurpose.PASSWORD_RESET


@pytest.fixture
def settings(make_settings):
    return make_settings(email_verification_expire_hours=24, password_reset_expire_minutes=60)


async def test_a_token_is_stored_as_a_hash_bound_to_the_address_and_the_purpose(
    db_session, settings, make_user, moving_clock
):
    user = await make_user()

    token = await email_token_service.issue(db_session, settings, user, RESET)

    row = await db_session.scalar(select(EmailToken))
    assert row.token_hash == security.hash_token(token)
    assert token.encode() not in row.token_hash
    assert (row.purpose, row.email, row.used_at) == (RESET, user.email, None)
    assert row.expires_at == moving_clock.now + email_token_service.lifetime(settings, RESET)


def test_each_purpose_has_its_own_lifetime(settings):
    assert email_token_service.lifetime(settings, VERIFY).total_seconds() == 24 * 3600
    assert email_token_service.lifetime(settings, RESET).total_seconds() == 60 * 60


async def test_a_token_works_once(db_session, settings, make_user):
    user = await make_user()
    token = await email_token_service.issue(db_session, settings, user, VERIFY)

    first = await email_token_service.redeem(db_session, token, VERIFY)
    second = await email_token_service.redeem(db_session, token, VERIFY)

    assert first is not None
    assert first.id == user.id
    assert second is None


async def test_a_token_of_another_purpose_or_an_unknown_one_is_refused(
    db_session, settings, make_user
):
    user = await make_user()
    token = await email_token_service.issue(db_session, settings, user, VERIFY)

    assert await email_token_service.redeem(db_session, token, RESET) is None
    assert await email_token_service.redeem(db_session, "no-such-token", VERIFY) is None
    # The wrong-purpose attempt did not spend it.
    assert await email_token_service.redeem(db_session, token, VERIFY) is not None


async def test_a_token_expires(db_session, settings, make_user, moving_clock):
    user = await make_user()
    token = await email_token_service.issue(db_session, settings, user, RESET)
    moving_clock.advance(minutes=61)

    assert await email_token_service.redeem(db_session, token, RESET) is None


async def test_a_new_token_cancels_the_earlier_one_of_the_same_purpose_only(
    db_session, settings, make_user
):
    user = await make_user()
    old_reset = await email_token_service.issue(db_session, settings, user, RESET)
    verify = await email_token_service.issue(db_session, settings, user, VERIFY)

    new_reset = await email_token_service.issue(db_session, settings, user, RESET)

    assert await email_token_service.redeem(db_session, old_reset, RESET) is None
    assert await email_token_service.redeem(db_session, new_reset, RESET) is not None
    assert await email_token_service.redeem(db_session, verify, VERIFY) is not None


async def test_cancelling_leaves_other_users_alone(db_session, settings, make_user):
    one, two = await make_user(), await make_user("two@example.com")
    token_one = await email_token_service.issue(db_session, settings, one, RESET)
    token_two = await email_token_service.issue(db_session, settings, two, RESET)

    await email_token_service.cancel_unused(db_session, one.id, RESET)

    assert await email_token_service.redeem(db_session, token_one, RESET) is None
    assert await email_token_service.redeem(db_session, token_two, RESET) is not None


async def test_a_token_dies_with_the_address_it_was_sent_to(db_session, settings, make_user):
    user = await make_user()
    token = await email_token_service.issue(db_session, settings, user, VERIFY)
    user.email = "moved@example.com"
    await db_session.flush()

    assert await email_token_service.redeem(db_session, token, VERIFY) is None


async def test_the_case_of_the_address_does_not_matter(db_session, settings, make_user):
    user = await make_user()
    token = await email_token_service.issue(db_session, settings, user, VERIFY)
    user.email = user.email.upper()
    await db_session.flush()

    assert await email_token_service.redeem(db_session, token, VERIFY) is not None


@pytest.mark.parametrize("change", ["disable", "delete"])
async def test_a_token_of_an_account_that_cannot_sign_in_is_refused(
    db_session, settings, make_user, moving_clock, change
):
    user = await make_user()
    token = await email_token_service.issue(db_session, settings, user, RESET)
    if change == "disable":
        user.is_active = False
    else:
        user.deleted_at = moving_clock.now
    await db_session.flush()

    assert await email_token_service.redeem(db_session, token, RESET) is None


async def test_expired_tokens_are_deleted_as_a_new_one_is_issued(
    db_session, settings, make_user, moving_clock
):
    user = await make_user()
    await email_token_service.issue(db_session, settings, user, RESET)
    moving_clock.advance(hours=2)

    await email_token_service.issue(db_session, settings, user, VERIFY)

    assert await db_session.scalar(select(func.count()).select_from(EmailToken)) == 1
