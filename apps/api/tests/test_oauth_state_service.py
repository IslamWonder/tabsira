from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from src import security
from src.models import OAuthState
from src.services import oauth_state_service as states


@pytest.fixture
def settings(make_settings):
    return make_settings(google_state_ttl_seconds=300)


@pytest.mark.parametrize(
    ("value", "safe"),
    [
        ("/world", True),
        ("/insights/12?tab=a#top", True),
        ("/", True),
        (None, False),
        ("", False),
        ("world", False),
        ("//evil.example", False),
        ("https://evil.example", False),
        ("/\\evil.example", False),
        ("/a\nb", False),
        ("/a\x7fb", False),
        ("/" + "a" * 200, False),
    ],
)
def test_only_a_path_inside_the_web_app_is_kept_as_the_return_address(value, safe):
    assert states.safe_next_path(value) == (value if safe else None)


async def test_a_started_flow_stores_hashes_of_the_state_and_the_binder_not_the_values(
    db_session, settings, moving_clock
):
    flow = await states.start(db_session, settings, "/world")

    row = await db_session.scalar(select(OAuthState))
    assert row.state_hash == security.hash_token(flow.state).hex()
    assert row.binder_hash == security.hash_token(flow.binder).hex()
    assert flow.state not in (row.state_hash, row.binder_hash)
    assert (row.code_verifier, row.nonce, row.next_path) == (flow.verifier, flow.nonce, "/world")
    assert 43 <= len(flow.verifier) <= 128
    assert row.expires_at == moving_clock.now + timedelta(seconds=300)
    assert len({flow.state, flow.binder, flow.nonce, flow.verifier}) == 4


async def test_a_state_works_once_for_the_browser_that_started_it(db_session, settings):
    flow = await states.start(db_session, settings, "/world")

    finished = await states.consume(db_session, flow.state, flow.binder)

    assert finished == states.FinishedFlow(
        verifier=flow.verifier, nonce=flow.nonce, next_path="/world"
    )
    assert await states.consume(db_session, flow.state, flow.binder) is None


async def test_an_unsafe_next_path_is_dropped_when_the_flow_starts(db_session, settings):
    flow = await states.start(db_session, settings, "//evil.example")

    finished = await states.consume(db_session, flow.state, flow.binder)

    assert finished is not None
    assert finished.next_path is None


@pytest.mark.parametrize("binder", [None, "another-browsers-cookie"])
async def test_a_state_from_another_browser_is_refused_and_spent(db_session, settings, binder):
    flow = await states.start(db_session, settings, None)

    assert await states.consume(db_session, flow.state, binder) is None
    # Spent by the attempt: the right browser cannot use it afterwards either.
    assert await states.consume(db_session, flow.state, flow.binder) is None


async def test_an_unknown_state_is_refused(db_session, settings):
    assert await states.consume(db_session, "never-issued", "binder") is None


async def test_a_state_expires(db_session, settings, moving_clock):
    flow = await states.start(db_session, settings, None)
    moving_clock.advance(seconds=301)

    assert await states.consume(db_session, flow.state, flow.binder) is None


async def test_expired_states_are_deleted_as_a_new_flow_starts(db_session, settings, moving_clock):
    await states.start(db_session, settings, None)
    moving_clock.advance(seconds=400)

    await states.start(db_session, settings, None)

    assert await db_session.scalar(select(func.count()).select_from(OAuthState)) == 1
