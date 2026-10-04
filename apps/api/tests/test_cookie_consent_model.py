"""The cookie-consent table: append-only, family-only, and gone with the account it belongs to."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from src.models import CookieConsent, User


async def make_user(db_session, email="a@example.com"):
    user = User(email=email, display_name="A")
    db_session.add(user)
    await db_session.flush()
    return user


def choice(**values):
    return CookieConsent(
        **{
            "consent_id": uuid.uuid4(),
            "policy_version": "2026-10-04",
            "analytics": True,
            "behaviour": False,
            "user_agent_family": "firefox",
            **values,
        }
    )


async def test_a_choice_has_a_time_ordered_id_the_necessary_category_on_and_a_time(db_session):
    row = choice()
    db_session.add(row)
    await db_session.flush()

    assert row.id.version == 7
    assert row.necessary is True
    assert row.created_at is not None
    assert row.user_id is None


async def test_the_necessary_category_cannot_be_turned_off(db_session):
    with pytest.raises(IntegrityError, match="ck_cookie_consents_necessary_always_on"):
        async with db_session.begin_nested():
            db_session.add(choice(necessary=False))
            await db_session.flush()


@pytest.mark.parametrize("family", ["Firefox", "Firefox/132.0", "Mozilla/5.0", ""])
async def test_only_a_browser_family_is_ever_stored_never_a_user_agent(db_session, family):
    with pytest.raises(IntegrityError, match="ck_cookie_consents_user_agent_family_known"):
        async with db_session.begin_nested():
            db_session.add(choice(user_agent_family=family))
            await db_session.flush()


async def test_a_full_user_agent_string_does_not_even_fit(db_session):
    full = "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/132.0"

    with pytest.raises(DBAPIError, match="too long"):
        async with db_session.begin_nested():
            db_session.add(choice(user_agent_family=full))
            await db_session.flush()


async def test_a_choice_can_be_added_but_never_edited(db_session):
    row = choice()
    db_session.add(row)
    await db_session.flush()

    with pytest.raises(DBAPIError, match="cookie_consents is append-only: UPDATE refused"):
        async with db_session.begin_nested():
            await db_session.execute(text("UPDATE app.cookie_consents SET analytics = false"))

    # Changing one's mind is a second row under the same id; the latest is the choice in force.
    db_session.add(choice(consent_id=row.consent_id, analytics=False))
    await db_session.flush()
    rows = (
        await db_session.scalars(
            select(CookieConsent)
            .where(CookieConsent.consent_id == row.consent_id)
            .order_by(CookieConsent.created_at, CookieConsent.id)
        )
    ).all()
    assert [r.analytics for r in rows] == [True, False]


@pytest.mark.parametrize("signed_in", [False, True])
async def test_a_choice_cannot_be_deleted_by_hand_signed_in_or_not(db_session, signed_in):
    user = await make_user(db_session) if signed_in else None
    db_session.add(choice(user_id=user.id if user else None))
    await db_session.flush()

    with pytest.raises(DBAPIError, match="cookie_consents is append-only: DELETE refused"):
        async with db_session.begin_nested():
            await db_session.execute(text("DELETE FROM app.cookie_consents"))


async def test_the_table_cannot_be_emptied_with_truncate(db_session):
    db_session.add(choice())
    await db_session.flush()

    with pytest.raises(DBAPIError, match="cookie_consents is append-only: TRUNCATE refused"):
        async with db_session.begin_nested():
            await db_session.execute(text("TRUNCATE app.cookie_consents"))


async def test_deleting_an_account_removes_its_choices_and_only_those(db_session):
    mine, other = (
        await make_user(db_session, "me@example.com"),
        await make_user(db_session, "you@example.com"),
    )
    anonymous = choice()
    db_session.add_all(
        [
            choice(user_id=mine.id),
            choice(user_id=mine.id, analytics=False),
            choice(user_id=other.id),
            anonymous,
        ]
    )
    await db_session.flush()

    await db_session.execute(text("DELETE FROM app.users WHERE id = :id"), {"id": mine.id})

    remaining = (await db_session.scalars(select(CookieConsent))).all()
    assert {row.user_id for row in remaining} == {other.id, None}
    assert len(remaining) == 2
