"""Cloudflare Turnstile verification: the HTTP call is replaced at the provider boundary."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator

import httpx
import pytest
from pydantic import ValidationError

from src.services import turnstile_service

SITE_KEY = "1x00000000000000000000AA"
SECRET = "1x0000000000000000000000000000AA"
TOKEN = "visitor-token-123"  # nosec B105


@pytest.fixture
def on(make_settings):
    return make_settings(turnstile_site_key=SITE_KEY, turnstile_secret_key=SECRET)


def answer(handler: Callable[[httpx.Request], httpx.Response]) -> list[httpx.Request]:
    """Make the shared client talk to `handler`; return the requests it receives."""
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    turnstile_service._client = httpx.AsyncClient(transport=httpx.MockTransport(record))
    return seen


@pytest.fixture(autouse=True)
def fresh_client() -> Iterator[None]:
    turnstile_service._client = None
    yield
    turnstile_service._client = None


def test_both_keys_empty_is_off(make_settings):
    settings = make_settings()

    assert settings.turnstile_enabled is False


def test_both_keys_set_is_on(on):
    assert on.turnstile_enabled is True


def test_a_site_key_alone_is_a_configuration_error_naming_the_missing_key(make_settings):
    with pytest.raises(ValidationError, match="TURNSTILE_SECRET_KEY"):
        make_settings(turnstile_site_key=SITE_KEY)


def test_a_secret_alone_is_a_configuration_error_naming_the_missing_key(make_settings):
    with pytest.raises(ValidationError, match="TURNSTILE_SITE_KEY"):
        make_settings(turnstile_secret_key=SECRET)


def test_the_secret_is_not_shown_when_the_settings_are_printed(on):
    assert SECRET not in repr(on)


async def test_off_passes_without_asking_cloudflare(make_settings):
    seen = answer(lambda _r: httpx.Response(500))

    assert await turnstile_service.verify(make_settings(), None) is True
    assert seen == []


async def test_a_missing_token_is_refused_without_asking_cloudflare(on):
    seen = answer(lambda _r: httpx.Response(200, json={"success": True}))

    assert await turnstile_service.verify(on, None) is False
    assert await turnstile_service.verify(on, "") is False
    assert seen == []


@pytest.mark.parametrize(
    "token",
    ["x" * 2049, "has space", "semi;colon", "new\nline", "tökén", "a&secret=b", "a=b"],
)
async def test_a_token_that_cannot_be_cloudflares_is_refused_without_a_call(on, token):
    seen = answer(lambda _r: httpx.Response(200, json={"success": True}))

    assert await turnstile_service.verify(on, token) is False
    assert seen == []


async def test_a_token_of_the_longest_length_and_every_allowed_character_is_sent(on):
    seen = answer(lambda _r: httpx.Response(200, json={"success": True}))
    token = ("aZ09-_." * 400)[:2048]

    assert await turnstile_service.verify(on, token) is True
    assert len(seen) == 1


async def test_an_accepted_token_passes_and_the_form_fields_are_sent(on):
    seen = answer(lambda _r: httpx.Response(200, json={"success": True}))

    assert await turnstile_service.verify(on, TOKEN, remote_ip="203.0.113.9") is True

    (request,) = seen
    assert str(request.url) == turnstile_service.VERIFY_URL
    assert request.method == "POST"
    assert request.content.decode() == f"secret={SECRET}&response={TOKEN}&remoteip=203.0.113.9"


async def test_no_address_means_no_remoteip_field(on):
    seen = answer(lambda _r: httpx.Response(200, json={"success": True}))

    await turnstile_service.verify(on, TOKEN)

    assert "remoteip" not in seen[0].content.decode()


async def test_a_refused_token_logs_only_cloudflares_codes(on, caplog):
    answer(
        lambda _r: httpx.Response(
            200, json={"success": False, "error-codes": ["timeout-or-duplicate"]}
        )
    )
    caplog.set_level(logging.INFO, logger="tabsira.turnstile")

    assert await turnstile_service.verify(on, TOKEN, remote_ip="203.0.113.9") is False

    assert "timeout-or-duplicate" in caplog.text
    assert TOKEN not in caplog.text
    assert "203.0.113.9" not in caplog.text
    assert SECRET not in caplog.text


async def test_a_refusal_without_a_list_of_codes_logs_an_empty_list(on, caplog):
    answer(lambda _r: httpx.Response(200, json={"success": False, "error-codes": "oops"}))
    caplog.set_level(logging.INFO, logger="tabsira.turnstile")

    assert await turnstile_service.verify(on, TOKEN) is False

    assert "refused a token: []" in caplog.text


@pytest.mark.parametrize("success", [None, "true", 1, "yes"])
async def test_only_a_real_true_counts_as_success(on, success):
    answer(lambda _r: httpx.Response(200, json={"success": success}))

    assert await turnstile_service.verify(on, TOKEN) is False


def raise_timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("slow", request=request)


def raise_network(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down", request=request)


@pytest.mark.parametrize(
    "handler",
    [
        raise_timeout,
        raise_network,
        lambda _r: httpx.Response(503, json={"success": True}),
        lambda _r: httpx.Response(200, content=b"<html>not json</html>"),
        lambda _r: httpx.Response(200, json=["success"]),
        lambda _r: httpx.Response(200, json="success"),
    ],
    ids=["timeout", "network", "http-error", "not-json", "list", "string"],
)
async def test_every_failure_means_not_verified(on, handler, caplog):
    answer(handler)
    caplog.set_level(logging.INFO, logger="tabsira.turnstile")

    assert await turnstile_service.verify(on, TOKEN, remote_ip="203.0.113.9") is False

    assert TOKEN not in caplog.text
    assert "203.0.113.9" not in caplog.text


async def test_the_client_is_shared_and_has_a_short_timeout():
    first = turnstile_service.http_client()

    assert turnstile_service.http_client() is first
    assert first.timeout.read == turnstile_service.VERIFY_TIMEOUT_SECONDS == 5.0
    await turnstile_service.close_http_client()
    assert first.is_closed
    assert turnstile_service._client is None


async def test_closing_without_a_client_does_nothing():
    await turnstile_service.close_http_client()

    assert turnstile_service._client is None
