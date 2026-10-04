"""The admin session: a separate cookie, twelve hours, and an account that must still be an admin."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from starlette.requests import Request
from starlette.responses import Response

from src import clock, security
from src.models import AdminSession
from src.services import admin_session_service as service


@pytest.fixture
def settings(make_settings):
    return make_settings()


def request_with(cookie=None):
    headers = [] if cookie is None else [(b"cookie", cookie.encode())]
    return Request({"type": "http", "method": "GET", "path": "/admin", "headers": headers})


async def sign_in(db, user, **kwargs):
    return await service.create(
        db, user_id=user.id, ip_hash="ip", user_agent=kwargs.get("user_agent")
    )


async def count(db):
    return await db.scalar(select(func.count()).select_from(AdminSession))


async def test_a_session_stores_the_hash_of_its_token_and_lives_twelve_hours(
    db_session, make_user, moving_clock
):
    admin = await make_user(is_admin=True)

    token = await sign_in(db_session, admin, user_agent="Firefox")

    row = await db_session.scalar(select(AdminSession))
    assert row.token_hash == security.hash_token(token)
    assert row.expires_at == moving_clock.now + timedelta(hours=12)
    assert (row.last_seen_at, row.ip_hash, row.user_agent) == (moving_clock.now, "ip", "Firefox")
    assert timedelta(hours=12) == service.ADMIN_SESSION_TTL


async def test_a_long_or_missing_user_agent_is_cut_or_left_empty(db_session, make_user):
    admin = await make_user(is_admin=True)

    await sign_in(db_session, admin, user_agent="x" * 1000)
    await sign_in(db_session, admin)

    agents = sorted((await db_session.scalars(select(AdminSession.user_agent))).all(), key=str)
    assert agents == [None, "x" * 256]


async def test_a_token_finds_its_session_and_admin_until_it_expires(
    db_session, make_user, moving_clock
):
    admin = await make_user(is_admin=True)
    token = await sign_in(db_session, admin)

    found = await service.find(db_session, token)
    assert found is not None
    assert found[1].id == admin.id
    assert await service.find(db_session, "not-the-token") is None

    moving_clock.advance(hours=12, seconds=1)
    assert await service.find(db_session, token) is None


@pytest.mark.parametrize(
    "change",
    [{"is_admin": False}, {"is_active": False}, {"deleted_at": "now"}],
    ids=["no longer admin", "deactivated", "deleted"],
)
async def test_an_account_that_stops_being_an_admin_loses_its_session_at_once(
    db_session, make_user, change
):
    admin = await make_user(is_admin=True)
    token = await sign_in(db_session, admin)
    for name, value in change.items():
        setattr(admin, name, clock.utcnow() if value == "now" else value)
    await db_session.flush()

    assert await service.find(db_session, token) is None


async def test_a_session_is_touched_at_most_every_five_minutes(db_session, make_user, moving_clock):
    admin = await make_user(is_admin=True)
    token = await sign_in(db_session, admin)
    found = await service.find(db_session, token)
    assert found is not None
    session = found[0]

    moving_clock.advance(minutes=4)
    assert await service.touch(db_session, session) is False
    moving_clock.advance(minutes=2)
    assert await service.touch(db_session, session) is True
    assert session.last_seen_at == moving_clock.now


async def test_creating_a_session_deletes_the_expired_ones(db_session, make_user, moving_clock):
    admin = await make_user(is_admin=True)
    await sign_in(db_session, admin)
    moving_clock.advance(hours=13)

    await sign_in(db_session, admin)

    assert await count(db_session) == 1


async def test_a_session_is_revoked_by_its_token_or_with_all_of_its_admin(db_session, make_user):
    one = await make_user("one@example.com", is_admin=True)
    two = await make_user("two@example.com", is_admin=True)
    first = await sign_in(db_session, one)
    await sign_in(db_session, one)
    other = await sign_in(db_session, two)

    await service.revoke(db_session, first)
    await service.revoke(db_session, "unknown-token")
    assert await count(db_session) == 2

    await service.revoke_all(db_session, one.id)
    assert await count(db_session) == 1
    assert await service.find(db_session, other) is not None


def test_the_cookie_is_httponly_secure_strict_and_confined_to_the_admin_path(settings):
    response = Response()

    service.set_cookie(response, settings, "the-token")

    header = response.headers["set-cookie"]
    assert header.startswith("__Secure-tabsira_admin=the-token;")
    assert "Max-Age=43200" in header
    assert "Path=/admin" in header
    for flag in ("HttpOnly", "Secure", "SameSite=strict"):
        assert flag in header
    assert "Domain" not in header


def test_clearing_the_cookie_expires_it_on_the_same_path(settings):
    response = Response()

    service.clear_cookie(response, settings)

    header = response.headers["set-cookie"]
    assert header.startswith('__Secure-tabsira_admin="";')
    assert "Max-Age=0" in header
    assert "Path=/admin" in header


def test_the_cookie_token_is_read_unless_it_is_missing_or_absurdly_long(settings):
    assert service.cookie_token(request_with(), settings) is None
    assert service.cookie_token(request_with("__Secure-tabsira_admin=abc"), settings) == "abc"
    assert (
        service.cookie_token(request_with(f"__Secure-tabsira_admin={'a' * 129}"), settings) is None
    )
    # The user cookie is another cookie and never opens the admin area.
    assert service.cookie_token(request_with("__Secure-tabsira_session=abc"), settings) is None


def test_over_plain_http_the_cookie_loses_its_secure_prefix_and_flag(make_settings):
    """Local development is http://tabsira.test (decision 49): a __Secure- cookie would be dropped."""
    settings = make_settings(
        site_url="http://tabsira.test",
        api_url="http://api.tabsira.test",
        admin_url="http://admin.tabsira.test",
        cors_origins="http://tabsira.test",
    )
    response = Response()

    service.set_cookie(response, settings, "the-token")

    header = response.headers["set-cookie"]
    assert header.startswith("tabsira_admin=the-token;")
    assert "Secure" not in header
    assert "HttpOnly" in header
    assert "SameSite=strict" in header
    assert service.cookie_token(request_with("tabsira_admin=abc"), settings) == "abc"
    assert service.cookie_token(request_with("__Secure-tabsira_admin=abc"), settings) is None


def test_the_csrf_token_follows_the_session_token_and_the_server_key(make_settings):
    settings = make_settings(hash_secret="one-secret-of-the-installation-123456")
    other = make_settings(hash_secret="another-secret-of-the-installation-1")

    token = service.csrf_token_for(settings, "session-token")

    assert token == service.csrf_token_for(settings, "session-token")
    assert token != service.csrf_token_for(settings, "another-session-token")
    assert token != service.csrf_token_for(other, "session-token")
    assert "session-token" not in token


async def test_a_credential_change_ends_the_admin_sessions_with_the_ordinary_ones(
    db_session, make_user
):
    from src.services import session_service

    admin = await make_user("admin@example.com", is_admin=True)
    other = await make_user("other@example.com", is_admin=True)
    mine = await sign_in(db_session, admin)
    theirs = await sign_in(db_session, other)

    await session_service.revoke_every_session(db_session, admin.id)

    assert await service.find(db_session, mine) is None
    assert await service.find(db_session, theirs) is not None
