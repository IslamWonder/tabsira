"""Cookie consent over HTTP: the policy, recording a choice, and what is in force."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select

from src.database import get_db
from src.main import create_app
from src.messages import messages_for
from src.models import CookieConsent
from src.routers import cookie_consent
from src.services.window_limiter import AddressLimits
from tests.conftest import BROWSER_ORIGIN, PASSPHRASE, browser_for

LOGIN = {"email": "reader@example.com", "password": PASSPHRASE}
FIREFOX = "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0"
CHOICE = {"analytics": True, "behaviour": False}


@pytest.fixture
def build_app(make_settings, db_session) -> Callable[..., FastAPI]:
    """Build the application on the test's session, with some settings changed."""

    def build(**values: Any) -> FastAPI:
        application = create_app(make_settings(password_bcrypt_rounds=4, **values))

        async def use_the_test_session() -> AsyncIterator[Any]:
            yield db_session

        application.dependency_overrides[get_db] = use_the_test_session
        return application

    return build


@pytest.fixture
async def visitor(build_app) -> AsyncIterator[AsyncClient]:
    """A browser that has not signed in."""
    async with browser_for(build_app()) as http:
        yield http


async def rows(db_session) -> list[CookieConsent]:
    result = await db_session.scalars(
        select(CookieConsent).order_by(CookieConsent.created_at, CookieConsent.id)
    )
    return list(result)


# ─── The policy ───────────────────────────────────────────────────────────────


async def test_the_policy_lists_the_three_categories_with_their_arabic_text(visitor):
    response = await visitor.get("/consent/policy")

    assert response.status_code == 200
    body = response.json()
    assert body["policy_version"] == "2026-10-04"
    assert body["reask_days"] == 182
    assert body["categories"] == [
        {
            "key": "necessary",
            "required": True,
            "title": messages_for().consent_necessary_title,
            "description": messages_for().consent_necessary_description,
        },
        {
            "key": "analytics",
            "required": False,
            "title": messages_for().consent_analytics_title,
            "description": messages_for().consent_analytics_description,
        },
        {
            "key": "behaviour",
            "required": False,
            "title": messages_for().consent_behaviour_title,
            "description": messages_for().consent_behaviour_description,
        },
    ]
    assert response.headers["cache-control"] == "no-store"


async def test_the_policy_follows_the_settings(build_app):
    async with browser_for(build_app(cookie_policy_version="v9", consent_reask_days=90)) as http:
        body = (await http.get("/consent/policy")).json()

    assert (body["policy_version"], body["reask_days"]) == ("v9", 90)


def test_every_category_text_is_arabic_and_names_what_is_never_sent():
    for text in (
        messages_for().consent_necessary_description,
        messages_for().consent_analytics_description,
        messages_for().consent_behaviour_description,
    ):
        assert any("؀" <= char <= "ۿ" for char in text)
    # The promises of decision 32, stated to the visitor.
    assert "ملفك الشخصي" in messages_for().consent_analytics_description
    assert "صورك" in messages_for().consent_analytics_description
    assert "كل خانة كتابة" in messages_for().consent_behaviour_description


# ─── Recording a choice ───────────────────────────────────────────────────────


async def test_the_first_choice_gets_a_random_id_made_by_the_server(visitor, db_session):
    response = await visitor.post("/consent", json=CHOICE, headers={"User-Agent": FIREFOX})

    assert response.status_code == 201
    body = response.json()
    consent_id = uuid.UUID(body["consent_id"])
    assert consent_id.version == 4
    assert body["policy_version"] == "2026-10-04"
    assert body["categories"] == {"necessary": True, "analytics": True, "behaviour": False}
    assert body["reask"] is False
    assert response.headers["cache-control"] == "no-store"
    (row,) = await rows(db_session)
    assert (row.consent_id, row.analytics, row.behaviour, row.necessary) == (
        consent_id,
        True,
        False,
        True,
    )
    assert row.user_id is None


async def test_what_is_kept_is_the_browser_family_and_no_address(visitor, db_session):
    await visitor.post("/consent", json=CHOICE, headers={"User-Agent": FIREFOX})
    await visitor.post("/consent", json=CHOICE)

    first, second = await rows(db_session)

    assert (first.user_agent_family, second.user_agent_family) == ("firefox", "other")
    columns = {column.name for column in CookieConsent.__table__.columns}
    assert not {name for name in columns if "ip" in name.split("_") or name == "user_agent"}
    stored = " ".join(str(getattr(first, name)) for name in columns)
    assert "132.0" not in stored
    assert "127.0.0.1" not in stored


async def test_a_second_choice_is_a_new_record_under_the_same_id(visitor, db_session):
    first = (await visitor.post("/consent", json=CHOICE)).json()

    second = await visitor.post(
        "/consent",
        json={"consent_id": first["consent_id"], "analytics": False, "behaviour": True},
    )

    assert second.status_code == 201
    body = second.json()
    assert body["consent_id"] == first["consent_id"]
    assert body["categories"] == {"necessary": True, "analytics": False, "behaviour": True}
    # Nothing was edited: both records are there, the latest one decides.
    earlier, later = await rows(db_session)
    assert (earlier.analytics, earlier.behaviour) == (True, False)
    assert (later.analytics, later.behaviour) == (False, True)
    current = (await visitor.get(f"/consent/{first['consent_id']}")).json()
    assert current["categories"] == body["categories"]


async def test_an_id_the_server_never_issued_is_not_adopted(visitor, db_session):
    invented = str(uuid.uuid4())

    response = await visitor.post("/consent", json={"consent_id": invented, **CHOICE})

    assert response.status_code == 201
    assert response.json()["consent_id"] != invented
    (row,) = await rows(db_session)
    assert str(row.consent_id) != invented


async def test_the_choice_of_a_signed_in_visitor_is_filed_under_their_account(
    build_app, make_user, db_session
):
    async with browser_for(build_app()) as web:
        user = await make_user()
        await web.post("/auth/login", json=LOGIN)

        response = await web.post("/consent", json=CHOICE)

    assert response.status_code == 201
    assert "user_id" not in response.json()
    (row,) = await rows(db_session)
    assert row.user_id == user.id


async def test_the_policy_version_the_visitor_was_shown_is_the_one_recorded(visitor, db_session):
    response = await visitor.post("/consent", json={**CHOICE, "policy_version": "2025-01-01"})

    body = response.json()
    assert body["policy_version"] == "2025-01-01"
    # It is not the current text any more, so the choice does not hold: ask again.
    assert body["reask"] is True
    assert body["categories"] == {"necessary": True, "analytics": False, "behaviour": False}
    (row,) = await rows(db_session)
    assert (row.policy_version, row.analytics) == ("2025-01-01", True)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"analytics": True},
        {"behaviour": True},
        {"analytics": "true", "behaviour": False},
        {"analytics": 1, "behaviour": 0},
        {"analytics": None, "behaviour": False},
        {**CHOICE, "necessary": False},
        {**CHOICE, "consent_id": "not-a-uuid"},
        {**CHOICE, "policy_version": "has space"},
        {**CHOICE, "policy_version": "x" * 33},
        {**CHOICE, "policy_version": ""},
    ],
)
async def test_a_choice_outside_the_schema_is_refused_and_nothing_is_recorded(
    visitor, db_session, body
):
    response = await visitor.post("/consent", json=body)

    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"
    assert await rows(db_session) == []


async def test_fields_the_route_does_not_know_are_ignored_not_stored(visitor, db_session):
    response = await visitor.post(
        "/consent",
        json={**CHOICE, "ip": "203.0.113.9", "email": "a@example.com", "necessary": True},
    )

    assert response.status_code == 201
    (row,) = await rows(db_session)
    assert "203.0.113.9" not in str(row.__dict__)


# ─── What is in force ─────────────────────────────────────────────────────────


async def test_a_choice_lapses_after_the_reask_interval(build_app, moving_clock):
    async with browser_for(build_app()) as http:
        made = (await http.post("/consent", json={"analytics": True, "behaviour": True})).json()
        moving_clock.advance(days=181)
        before = (await http.get(f"/consent/{made['consent_id']}")).json()
        moving_clock.advance(days=1)
        after = (await http.get(f"/consent/{made['consent_id']}")).json()

    assert before["reask"] is False
    assert before["categories"] == {"necessary": True, "analytics": True, "behaviour": True}
    assert after["reask"] is True
    # What was chosen no longer runs; the necessary category always does.
    assert after["categories"] == {"necessary": True, "analytics": False, "behaviour": False}
    assert after["policy_version"] == made["policy_version"]
    decided = after["decided_at"]
    assert decided == made["decided_at"]


async def test_the_expiry_is_the_decision_plus_the_interval(build_app, moving_clock):
    async with browser_for(build_app(consent_reask_days=30)) as http:
        body = (await http.post("/consent", json=CHOICE)).json()

    assert body["decided_at"] == moving_clock.now.isoformat().replace("+00:00", "Z")
    assert body["expires_at"] == (moving_clock.now + timedelta(days=30)).isoformat().replace(
        "+00:00", "Z"
    )


async def test_a_new_policy_version_asks_everyone_again(build_app):
    async with browser_for(build_app(cookie_policy_version="v1")) as old:
        made = (await old.post("/consent", json=CHOICE)).json()
        assert made["reask"] is False
    async with browser_for(build_app(cookie_policy_version="v2")) as new:
        now = (await new.get(f"/consent/{made['consent_id']}")).json()

    assert now["reask"] is True
    assert now["policy_version"] == "v1"
    assert now["categories"] == {"necessary": True, "analytics": False, "behaviour": False}


async def test_an_id_that_was_never_issued_is_a_404_in_the_usual_body(visitor):
    response = await visitor.get(f"/consent/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"] == "NOT_FOUND"
    assert response.headers["cache-control"] == "no-store"


async def test_an_id_that_is_not_a_uuid_is_a_validation_error(visitor):
    response = await visitor.get("/consent/not-a-uuid")

    assert response.status_code == 422


async def test_reading_a_choice_needs_no_session_and_shows_no_account(build_app, make_user):
    async with browser_for(build_app()) as web:
        await make_user()
        await web.post("/auth/login", json=LOGIN)
        made = (await web.post("/consent", json=CHOICE)).json()
    async with browser_for(build_app()) as stranger:
        shown = await stranger.get(f"/consent/{made['consent_id']}")

    assert shown.status_code == 200
    assert shown.json() == made


# ─── Bounds ───────────────────────────────────────────────────────────────────


async def test_a_body_over_the_cap_is_refused_before_it_is_read(visitor, db_session):
    big = b'{"analytics": true, "behaviour": true, "x": "' + b"a" * 5000 + b'"}'

    response = await visitor.post(
        "/consent", content=big, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 413
    assert response.json()["error"] == "PAYLOAD_TOO_LARGE"
    assert len(big) > cookie_consent.MAX_BODY_BYTES
    assert await rows(db_session) == []


async def test_an_address_that_records_too_many_choices_is_told_to_wait(build_app, db_session):
    application = build_app()
    application.state.consent_limits = AddressLimits(2, 600, 300)

    async with browser_for(application) as http:
        statuses = [(await http.post("/consent", json=CHOICE)).status_code for _ in range(4)]
        refused = await http.post("/consent", json=CHOICE)

    assert statuses == [201, 201, 429, 429]
    assert refused.json()["error"] == "RATE_LIMITED"
    assert int(refused.headers["retry-after"]) >= 1
    # A refused choice is not recorded.
    assert len(await rows(db_session)) == 2


async def test_every_address_together_is_bounded_too(build_app):
    application = build_app()
    application.state.consent_limits = AddressLimits(30, 2, 300)

    async with browser_for(application) as http:
        statuses = [(await http.post("/consent", json=CHOICE)).status_code for _ in range(3)]

    assert statuses == [201, 201, 429]


async def test_a_page_of_another_origin_cannot_record_a_choice(visitor, db_session):
    response = await visitor.post(
        "/consent", json=CHOICE, headers={"Origin": "https://evil.example"}
    )

    assert response.status_code == 403
    assert response.json()["error"] == "ORIGIN_NOT_ALLOWED"
    assert await rows(db_session) == []


async def test_the_web_app_may_call_the_route_across_origins(visitor):
    preflight = await visitor.options(
        "/consent",
        headers={
            "Origin": BROWSER_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == BROWSER_ORIGIN


async def test_the_routes_are_in_the_published_schema(visitor):
    schema = (await visitor.get("/openapi.json")).json()

    paths = schema["paths"]
    assert {"/consent", "/consent/policy", "/consent/{consent_id}"} <= set(paths)
    assert paths["/consent"]["post"]["tags"] == ["consent"]
    assert "201" in paths["/consent"]["post"]["responses"]
    assert {"CookieConsentIn", "CookieConsentOut", "ConsentPolicyOut"} <= set(
        schema["components"]["schemas"]
    )


async def test_the_database_rows_of_two_browsers_stay_apart(visitor, db_session):
    one = (await visitor.post("/consent", json=CHOICE)).json()
    two = (await visitor.post("/consent", json={"analytics": False, "behaviour": False})).json()

    assert one["consent_id"] != two["consent_id"]
    assert await db_session.scalar(select(func.count()).select_from(CookieConsent)) == 2
    assert (await visitor.get(f"/consent/{one['consent_id']}")).json()["categories"][
        "analytics"
    ] is True
