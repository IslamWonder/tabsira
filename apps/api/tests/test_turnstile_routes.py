"""The five protected routes refuse without a Turnstile token, before any bookkeeping."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from src.config import Settings
from src.database import get_db
from src.main import create_app
from src.models import LoginAttempt, User
from src.services import turnstile_service
from tests.conftest import BROWSER_ORIGIN, browser_for
from tests.test_auth_routes import LOGIN, SIGNUP
from tests.test_support_routes import BODY as SUPPORT

GOOD = "good-token"
EMAIL = {"email": "reader@example.com"}
ROUTES = [
    ("/auth/signup", SIGNUP),
    ("/auth/login", LOGIN),
    ("/auth/forgot-password", EMAIL),
    ("/auth/resend-verification", EMAIL),
    ("/support", SUPPORT),
]


class FakeVerifier:
    """Stands for Cloudflare: accepts one token, remembers what it was asked."""

    def __init__(self) -> None:
        self.asked: list[tuple[str | None, str | None]] = []

    async def __call__(
        self, _settings: Settings, token: str | None, *, remote_ip: str | None = None
    ) -> bool:
        self.asked.append((token, remote_ip))
        return token == GOOD


@pytest.fixture
def verifier(monkeypatch: pytest.MonkeyPatch) -> FakeVerifier:
    fake = FakeVerifier()
    monkeypatch.setattr(turnstile_service, "verify", fake)
    return fake


def application(
    make_settings: Callable[..., Settings], db_session: AsyncSession, **values: Any
) -> FastAPI:
    settings = make_settings(
        password_bcrypt_rounds=4,
        smtp_host="smtp.example.com",
        smtp_username="mailer",
        smtp_password="mailer-password",
        **values,
    )
    app = create_app(settings)

    async def use_the_test_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = use_the_test_session
    return app


@pytest.fixture
async def guarded(make_settings, db_session, mailbox, verifier) -> AsyncIterator[AsyncClient]:
    app = application(
        make_settings,
        db_session,
        turnstile_site_key="1x00000000000000000000AA",
        turnstile_secret_key="1x0000000000000000000000000000AA",
    )
    async with browser_for(app) as http:
        yield http


@pytest.fixture
async def unguarded(make_settings, db_session, mailbox, verifier) -> AsyncIterator[AsyncClient]:
    async with browser_for(application(make_settings, db_session)) as http:
        yield http


async def count(db: AsyncSession, model: type) -> int:
    return await db.scalar(select(func.count()).select_from(model)) or 0


@pytest.mark.parametrize(("path", "body"), ROUTES)
async def test_a_request_without_a_token_is_refused_with_403(guarded, path, body):
    response = await guarded.post(path, json=body)

    assert response.status_code == 403
    assert response.json()["error"] == "turnstile_failed"
    assert response.json()["detail"] == "تعذّر التحقق من أنك لست روبوتًا. أعد المحاولة."


@pytest.mark.parametrize(("path", "body"), ROUTES)
async def test_a_refused_token_touches_nothing_and_is_not_counted(
    guarded, db_session, mailbox, path, body
):
    for _ in range(30):  # far over every limit of the five routes
        response = await guarded.post(path, json=body, headers={"CF-Turnstile-Response": "bad"})
        assert response.status_code == 403

    assert await count(db_session, LoginAttempt) == 0
    assert await count(db_session, User) == 0
    assert mailbox == []


@pytest.mark.parametrize(("path", "body"), ROUTES)
async def test_a_good_token_lets_the_route_do_its_work(guarded, path, body):
    if path == "/auth/login":
        await guarded.post("/auth/signup", json=SIGNUP, headers={"CF-Turnstile-Response": GOOD})

    response = await guarded.post(path, json=body, headers={"CF-Turnstile-Response": GOOD})

    assert response.status_code in {200, 201, 202}


async def test_the_token_comes_from_the_header_with_the_visitors_address(guarded, verifier):
    await guarded.post("/auth/forgot-password", json=EMAIL, headers={"cf-turnstile-response": GOOD})

    assert verifier.asked == [(GOOD, "127.0.0.1")]


async def test_a_token_in_the_body_is_ignored(guarded):
    response = await guarded.post("/auth/forgot-password", json={**EMAIL, "token": GOOD})

    assert response.status_code == 403


async def test_a_refusal_comes_before_the_body_is_validated(guarded):
    response = await guarded.post("/auth/signup", json={"email": "nope"})

    assert response.status_code == 403


async def test_a_visitor_without_an_address_is_still_checked(guarded, verifier, monkeypatch):
    monkeypatch.setattr(Request, "client", property(lambda _self: None))

    response = await guarded.post("/auth/forgot-password", json=EMAIL)

    assert response.status_code == 403
    assert verifier.asked == [(None, None)]


@pytest.mark.parametrize(("path", "body"), ROUTES)
async def test_off_every_route_passes_without_a_token(unguarded, verifier, path, body):
    if path == "/auth/login":
        await unguarded.post("/auth/signup", json=SIGNUP)

    response = await unguarded.post(path, json=body)

    assert response.status_code in {200, 201, 202}
    assert verifier.asked == []


async def test_other_routes_do_not_ask_for_a_token(guarded, verifier):
    response = await guarded.get("/auth/providers")

    assert response.status_code == 200
    assert verifier.asked == []


async def test_the_header_passes_a_credentialed_preflight(guarded):
    response = await guarded.options(
        "/auth/login",
        headers={
            "Origin": BROWSER_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,cf-turnstile-response",
        },
    )

    assert response.status_code == 200
    assert "cf-turnstile-response" in response.headers["access-control-allow-headers"].lower()
    assert response.headers["access-control-allow-credentials"] == "true"


async def test_the_openapi_schema_has_no_token_parameter(guarded):
    schema = (await guarded.get("/openapi.json")).text

    # The error code joins the ErrorCode enum; no route declares the header as a parameter.
    assert "cf-turnstile-response" not in schema.lower()
