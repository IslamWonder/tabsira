from __future__ import annotations

import pytest

from src.main import create_app
from tests.helpers import client_for


@pytest.fixture
async def client(make_settings):
    application = create_app(make_settings())

    @application.get("/auth/_private")
    async def private() -> dict[str, int]:
        return {"a": 1}

    @application.get("/public")
    async def public() -> dict[str, int]:
        return {"a": 1}

    async with client_for(application) as http:
        yield http


@pytest.mark.parametrize(
    "path",
    [
        "/auth/me",
        "/auth/providers",
        "/auth/_private",
        "/profile",
        "/account/export",
        "/atlas/entries/1",
        "/atlas/places/1",
    ],
)
async def test_private_routes_are_never_cached_even_when_they_fail(client, path):
    response = await client.get(path)

    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["/public", "/health", "/openapi.json"])
async def test_other_routes_are_left_alone(client, path):
    response = await client.get(path)

    assert "cache-control" not in response.headers


async def test_a_consent_post_and_an_account_delete_are_not_cached_either(client):
    assert (await client.post("/consents", json={})).headers["cache-control"] == "no-store"
    assert (await client.delete("/account")).headers["cache-control"] == "no-store"


async def test_other_scope_types_pass_through(make_settings):
    from src.middleware.no_store import NoStoreMiddleware

    seen = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    middleware = NoStoreMiddleware(app)

    await middleware({"type": "lifespan"}, None, None)

    assert seen == ["lifespan"]
