from __future__ import annotations

import pytest

from src import main
from src.config import Settings
from tests.helpers import client_for


async def test_openapi_is_published_with_the_health_routes(client):
    response = await client.get("/openapi.json")

    schema = response.json()
    assert response.status_code == 200
    assert schema["info"]["title"] == "TABSIRA API"
    assert schema["info"]["version"] == main.API_VERSION
    assert {"/health", "/health/ready"} <= set(schema["paths"])
    assert "Readiness" in schema["components"]["schemas"]


async def test_every_route_documents_the_one_error_body(client):
    schema = (await client.get("/openapi.json")).json()

    error = schema["components"]["schemas"]["ErrorResponse"]
    assert set(error["properties"]) == {
        "error",
        "detail",
        "fields",
        "terms_version",
        "privacy_version",
    }
    assert error["required"] == ["error", "detail"]
    assert "NOT_FOUND" in schema["components"]["schemas"]["ErrorCode"]["enum"]
    for path in ("/health", "/health/ready"):
        responses = schema["paths"][path]["get"]["responses"]
        assert responses["default"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorResponse"
        }
    assert "HTTPValidationError" not in schema["components"]["schemas"]


async def test_interactive_docs_exist_outside_production(client):
    assert (await client.get("/docs")).status_code == 200
    assert (await client.get("/redoc")).status_code == 200


async def test_production_serves_the_schema_but_not_the_interactive_docs(make_settings):
    settings = make_settings(
        environment="production",
        site_url="https://tabsira.me",
        api_url="https://api.tabsira.me",
        admin_url="https://admin.tabsira.me",
        cors_origins="https://tabsira.me",
        session_cookie_domain=".tabsira.me",
        hash_secret="not-a-real-secret-but-long-enough-for-the-rule",
        admin_totp_encryption_key="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
        ai_ovh={"api_key": "ovh-key-123"},
        ai_openai={"api_key": "openai-key-123"},
        redis_password="redis-secret",
    )
    async with client_for(main.create_app(settings)) as client:
        assert (await client.get("/openapi.json")).status_code == 200
        for path in ("/docs", "/redoc"):
            response = await client.get(path)
            assert response.status_code == 404
            assert response.json()["error"] == "NOT_FOUND"


def test_the_module_level_app_is_built_from_the_environment(app):
    assert isinstance(main.app.state.settings, Settings)
    assert main.app.state.settings.environment.value == "test"


def test_create_app_uses_the_settings_it_is_given(make_settings):
    settings = make_settings(cors_origins="https://one.example")

    assert main.create_app(settings).state.settings is settings


async def test_cors_allows_a_listed_origin_and_exposes_the_request_id(make_settings):
    settings = make_settings(cors_origins="https://tabsira.me,https://www.tabsira.me")
    async with client_for(main.create_app(settings)) as client:
        preflight = await client.options(
            "/health",
            headers={
                "Origin": "https://tabsira.me",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        simple = await client.get("/health", headers={"Origin": "https://www.tabsira.me"})

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "https://tabsira.me"
    assert preflight.headers["access-control-allow-credentials"] == "true"
    assert simple.headers["access-control-allow-origin"] == "https://www.tabsira.me"
    assert simple.headers["access-control-expose-headers"] == "X-Request-ID"


@pytest.mark.parametrize("origin", ["https://evil.example", "http://tabsira.me"])
async def test_cors_refuses_an_unlisted_origin(make_settings, origin):
    async with client_for(main.create_app(make_settings(cors_origins="https://tabsira.me"))) as c:
        preflight = await c.options(
            "/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"}
        )
        simple = await c.get("/health", headers={"Origin": origin})

    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers
    assert "access-control-allow-origin" not in simple.headers


async def test_the_lifespan_closes_the_database_connections_on_shutdown(app, monkeypatch):
    calls: list[str] = []

    async def fake_dispose() -> None:
        calls.append("disposed")

    monkeypatch.setattr(main, "dispose_engine", fake_dispose)
    monkeypatch.setattr(main, "shutdown_error_tracking", lambda: calls.append("flushed"))

    async with app.router.lifespan_context(app):
        assert calls == []

    # The error reports go out before the connections are dropped.
    assert calls == ["flushed", "disposed"]


async def test_the_lifespan_also_flushes_the_forwarder_of_browser_reports(
    make_settings, monkeypatch
):
    application = main.create_app(make_settings())
    flushed: list[str] = []

    class Reporter:
        def flush(self) -> None:
            flushed.append("web")

    application.state.web_reporter = Reporter()

    async def fake_dispose() -> None:
        return None

    monkeypatch.setattr(main, "dispose_engine", fake_dispose)
    async with application.router.lifespan_context(application):
        pass

    assert flushed == ["web"]


def test_the_application_starts_error_tracking_before_it_is_built(make_settings, monkeypatch):
    started: list[tuple[Settings, str]] = []
    monkeypatch.setattr(
        main, "init_error_tracking", lambda settings, version: started.append((settings, version))
    )
    settings = make_settings()

    main.create_app(settings)

    assert started == [(settings, main.API_VERSION)]
