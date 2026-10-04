from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from starlette.requests import Request
from starlette.responses import Response

from src import security
from src.models import Session
from src.services import session_service


@pytest.fixture
def settings(make_settings):
    return make_settings(session_ttl_days=7)


def request_with(cookie=None, user_agent=None):
    headers = []
    if cookie is not None:
        headers.append((b"cookie", cookie.encode()))
    if user_agent is not None:
        headers.append((b"user-agent", user_agent.encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


async def sign_in(db, settings, user, **kwargs):
    return await session_service.create(
        db, settings, user_id=user.id, ip_hash="ip", user_agent=kwargs.get("user_agent")
    )


async def test_a_session_stores_the_hash_of_its_token_and_nothing_that_replays_it(
    db_session, settings, make_user, moving_clock
):
    user = await make_user()

    token = await sign_in(db_session, settings, user, user_agent="Firefox")

    row = await db_session.scalar(select(Session))
    assert row.token_hash == security.hash_token(token)
    assert token.encode() not in row.token_hash
    assert row.expires_at == moving_clock.now + timedelta(days=7)
    assert (row.last_seen_at, row.ip_hash, row.user_agent) == (moving_clock.now, "ip", "Firefox")


async def test_a_long_or_missing_user_agent_is_cut_or_left_empty(db_session, settings, make_user):
    user = await make_user()

    await sign_in(db_session, settings, user, user_agent="x" * 1000)
    await sign_in(db_session, settings, user)

    agents = sorted(
        (await db_session.scalars(select(Session.user_agent))).all(), key=lambda a: a or ""
    )
    assert agents == [None, "x" * 256]


async def test_a_token_finds_its_session_and_account_until_it_expires(
    db_session, settings, make_user, moving_clock
):
    user = await make_user()
    token = await sign_in(db_session, settings, user)

    found = await session_service.find(db_session, token)
    assert found is not None
    assert found[1].id == user.id
    assert await session_service.find(db_session, "not-the-token") is None

    moving_clock.advance(days=7, seconds=1)
    assert await session_service.find(db_session, token) is None


async def test_a_disabled_or_deleted_account_has_no_session(
    db_session, settings, make_user, moving_clock
):
    user = await make_user()
    token = await sign_in(db_session, settings, user)

    user.is_active = False
    await db_session.flush()
    assert await session_service.find(db_session, token) is None

    user.is_active = True
    user.deleted_at = moving_clock.now
    await db_session.flush()
    assert await session_service.find(db_session, token) is None


async def test_expired_sessions_are_deleted_as_a_new_one_is_made(
    db_session, settings, make_user, moving_clock
):
    user = await make_user()
    await sign_in(db_session, settings, user)
    moving_clock.advance(days=8)

    await sign_in(db_session, settings, user)

    assert await db_session.scalar(select(func.count()).select_from(Session)) == 1


async def test_last_seen_is_written_at_most_every_five_minutes(
    db_session, settings, make_user, moving_clock
):
    user = await make_user()
    token = await sign_in(db_session, settings, user)
    session, _ = await session_service.find(db_session, token)
    first_seen = session.last_seen_at

    moving_clock.advance(minutes=4)
    assert await session_service.touch(db_session, session) is False
    assert session.last_seen_at == first_seen

    moving_clock.advance(minutes=2)
    assert await session_service.touch(db_session, session) is True
    assert session.last_seen_at == moving_clock.now


async def test_revoking_ends_one_session_and_ignores_an_unknown_token(
    db_session, settings, make_user
):
    user = await make_user()
    one, two = await sign_in(db_session, settings, user), await sign_in(db_session, settings, user)

    await session_service.revoke(db_session, one)
    await session_service.revoke(db_session, "unknown")

    assert await session_service.find(db_session, one) is None
    assert await session_service.find(db_session, two) is not None


async def test_revoking_all_ends_every_session_except_the_one_kept(db_session, settings, make_user):
    user, other = await make_user(), await make_user("other@example.com")
    one, two = await sign_in(db_session, settings, user), await sign_in(db_session, settings, user)
    theirs = await sign_in(db_session, settings, other)

    await session_service.revoke_all(db_session, user.id, keep_token=two)

    assert await session_service.find(db_session, one) is None
    assert await session_service.find(db_session, two) is not None
    assert await session_service.find(db_session, theirs) is not None

    await session_service.revoke_all(db_session, user.id)
    assert await session_service.find(db_session, two) is None


def test_the_cookie_token_is_read_by_name_and_refused_when_absurdly_long(settings):
    name = settings.session_cookie_name

    assert session_service.cookie_token(request_with(f"{name}=abc"), settings) == "abc"
    assert session_service.cookie_token(request_with("other=abc"), settings) is None
    assert session_service.cookie_token(request_with(), settings) is None
    assert session_service.cookie_token(request_with(f"{name}={'x' * 129}"), settings) is None


def test_the_cookie_is_http_only_secure_same_site_lax_on_the_shared_domain(settings):
    response = Response()

    session_service.set_cookie(response, settings, "tok")

    cookie = response.headers["set-cookie"]
    assert cookie.startswith("__Secure-tabsira_session=tok;")
    assert "HttpOnly" in cookie
    # The attribute, not the name: `__Secure-` already contains the word.
    assert "; Secure" in cookie
    assert "SameSite=lax" in cookie
    assert "Domain=.tabsira.test" in cookie
    assert "Max-Age=604800" in cookie
    assert "Path=/" in cookie


def test_over_plain_http_the_cookie_loses_its_secure_prefix_and_flag(make_settings):
    """Local development is http://tabsira.test (decision 49): a __Secure- cookie would be dropped."""
    settings = make_settings(
        site_url="http://tabsira.test",
        api_url="http://api.tabsira.test",
        admin_url="http://admin.tabsira.test",
        cors_origins="http://tabsira.test",
    )
    response = Response()

    session_service.set_cookie(response, settings, "tok")

    cookie = response.headers["set-cookie"]
    assert cookie.startswith("tabsira_session=tok;")
    assert "; Secure" not in cookie
    assert "HttpOnly" in cookie
    assert "Domain=.tabsira.test" in cookie
    assert session_service.cookie_token(request_with("tabsira_session=abc"), settings) == "abc"
    assert (
        session_service.cookie_token(request_with("__Secure-tabsira_session=abc"), settings) is None
    )


def test_clearing_the_cookie_expires_it_on_the_same_domain_and_path(settings):
    response = Response()

    session_service.clear_cookie(response, settings)

    cookie = response.headers["set-cookie"]
    assert cookie.startswith('__Secure-tabsira_session="";')
    assert "Max-Age=0" in cookie
    assert "Domain=.tabsira.test" in cookie
    assert "; Secure" in cookie


def test_an_empty_domain_makes_a_host_only_cookie(make_settings):
    response = Response()

    session_service.set_cookie(response, make_settings(session_cookie_domain=""), "tok")

    assert "Domain" not in response.headers["set-cookie"]


async def test_starting_a_session_ends_the_one_the_browser_held(db_session, settings, make_user):
    user = await make_user()
    old = await sign_in(db_session, settings, user)
    request = request_with(f"{settings.session_cookie_name}={old}", user_agent="Safari")

    new = await session_service.start_for_request(
        db_session, settings, request, user_id=user.id, ip_hash="ip"
    )

    assert new != old
    assert await session_service.find(db_session, old) is None
    found = await session_service.find(db_session, new)
    assert found is not None
    assert found[0].user_agent == "Safari"


async def test_starting_a_session_with_no_cookie_just_opens_one(db_session, settings, make_user):
    user = await make_user()

    token = await session_service.start_for_request(
        db_session, settings, request_with(), user_id=user.id, ip_hash="ip"
    )

    assert await session_service.find(db_session, token) is not None
