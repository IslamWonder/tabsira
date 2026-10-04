"""Photo addresses: public addresses, default ports, three redirects, 12 s, 15 MB, image/*."""

from __future__ import annotations

import asyncio
import socket

import httpcore
import httpx
import pytest

from src.scans import fetch
from src.scans.fetch import (
    FetchError,
    FetchRefusal,
    PublicOnlyBackend,
    check_addresses,
    check_url,
    fetch_client,
    fetch_image,
    is_public,
)

PUBLIC = "93.184.216.34"


def resolver_of(table: dict[str, list[str]]):
    async def resolve(host: str, port: int) -> list[str]:
        del port
        if is_public(host) or host.replace(".", "").isdigit():
            return [host]
        if host not in table:
            message = "no such name"
            raise socket.gaierror(message)
        return table[host]

    return resolve


PUBLIC_NAMES = resolver_of(
    {"photos.example": [PUBLIC], "cdn.example": [PUBLIC], "mixed.example": [PUBLIC, "10.0.0.1"]}
)


@pytest.mark.parametrize(
    ("address", "public"),
    [
        (PUBLIC, True),
        ("2606:2800:220:1:248:1893:25c8:1946", True),
        ("127.0.0.1", False),
        ("10.1.2.3", False),
        ("172.16.0.1", False),
        ("192.168.1.1", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),
        ("0.0.0.0", False),  # noqa: S104 - an address to classify, nothing binds
        ("224.0.0.1", False),
        ("240.0.0.1", False),
        ("::1", False),
        ("fe80::1%eth0", False),
        ("fc00::1", False),
        ("::ffff:127.0.0.1", False),
        ("::ffff:93.184.216.34", True),
        ("not an address", False),
    ],
)
def test_only_global_unicast_addresses_are_public(address, public):
    assert is_public(address) is public


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://photos.example/a.jpg", ("photos.example", 443)),
        ("http://photos.example/a.jpg", ("photos.example", 80)),
        ("https://photos.example:443/a.jpg", ("photos.example", 443)),
    ],
)
def test_an_address_on_a_default_port_is_accepted(url, expected):
    assert check_url(url) == expected


@pytest.mark.parametrize(
    ("url", "refusal"),
    [
        ("ftp://photos.example/a.jpg", FetchRefusal.INVALID_URL),
        ("file:///etc/passwd", FetchRefusal.INVALID_URL),
        ("https:///a.jpg", FetchRefusal.INVALID_URL),
        ("https://user:pw@photos.example/a.jpg", FetchRefusal.INVALID_URL),
        ("https://photos.example:8443/a.jpg", FetchRefusal.FORBIDDEN_ADDRESS),
        ("http://photos.example:443/a.jpg", FetchRefusal.FORBIDDEN_ADDRESS),
        ("https://photos.example:99999/a.jpg", FetchRefusal.INVALID_URL),
        ("https://photos.example/" + "a" * 2100, FetchRefusal.INVALID_URL),
    ],
)
def test_other_addresses_are_refused_before_any_request(url, refusal):
    with pytest.raises(FetchError) as caught:
        check_url(url)
    assert caught.value.refusal is refusal


async def test_every_address_of_a_name_must_be_public():
    assert await check_addresses("photos.example", 443, PUBLIC_NAMES) == [PUBLIC]
    for host, refusal in (
        ("mixed.example", FetchRefusal.FORBIDDEN_ADDRESS),
        ("unknown.example", FetchRefusal.UNREACHABLE),
    ):
        with pytest.raises(FetchError) as caught:
            await check_addresses(host, 443, PUBLIC_NAMES)
        assert caught.value.refusal is refusal
    with pytest.raises(FetchError) as caught:
        await check_addresses("empty.example", 443, resolver_of({"empty.example": []}))
    assert caught.value.refusal is FetchRefusal.UNREACHABLE


async def test_the_system_resolver_answers_addresses():
    assert "127.0.0.1" in await fetch.system_resolver("127.0.0.1", 80)


async def test_the_connection_goes_only_to_an_address_just_checked(monkeypatch):
    connected: list[tuple[str, int]] = []

    async def connect_tcp(self, host, port, *_args, **_kwargs):
        connected.append((host, port))
        return "stream"

    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", connect_tcp)
    slept: list[float] = []

    async def sleep(self, seconds):
        slept.append(seconds)

    monkeypatch.setattr(httpcore.AnyIOBackend, "sleep", sleep)
    backend = PublicOnlyBackend(
        resolver_of({"photos.example": [PUBLIC], "rebound.example": ["127.0.0.1"]})
    )

    assert await backend.connect_tcp("photos.example", 443) == "stream"
    assert connected == [(PUBLIC, 443)]
    with pytest.raises(httpcore.ConnectError, match="non-public"):
        await backend.connect_tcp("rebound.example", 443)
    with pytest.raises(httpcore.ConnectError, match="unix sockets"):
        await backend.connect_unix_socket("/run/x.sock")
    await backend.sleep(0.1)
    assert slept == [0.1]


async def test_the_fetch_client_follows_no_redirect_and_reads_no_proxy(flow_settings):
    async with fetch_client(flow_settings) as client:
        assert client.follow_redirects is False
        assert client.headers["user-agent"] == fetch.USER_AGENT
        assert client.headers["accept-encoding"] == "identity"
        assert isinstance(client._transport, fetch.PublicOnlyTransport)
        assert client.timeout.read == 12.0


def client_of(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)


async def chunks(*sizes: int):
    for size in sizes:
        yield b"x" * size


def image(content: object = b"\xff\xd8\xffjpeg", **headers: str) -> httpx.Response:
    return httpx.Response(200, content=content, headers={"content-type": "image/jpeg", **headers})


async def test_a_photo_is_fetched_through_redirects_each_checked(flow_settings):
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/moved"})
        if request.url.path == "/moved":
            return httpx.Response(301, headers={"location": "https://cdn.example/photo.jpg"})
        return image(b"PHOTO")

    async with client_of(handler) as client:
        data = await fetch_image(
            "https://photos.example/start", flow_settings, client=client, resolver=PUBLIC_NAMES
        )

    assert data == b"PHOTO"
    assert asked == [
        "https://photos.example/start",
        "https://photos.example/moved",
        "https://cdn.example/photo.jpg",
    ]


async def test_a_redirect_to_a_private_address_is_refused(flow_settings):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})

    async with client_of(handler) as client:
        with pytest.raises(FetchError) as caught:
            await fetch_image(
                "https://photos.example/a", flow_settings, client=client, resolver=PUBLIC_NAMES
            )
    assert caught.value.refusal is FetchRefusal.FORBIDDEN_ADDRESS


@pytest.mark.parametrize(
    ("handler", "refusal"),
    [
        (
            lambda r: httpx.Response(302, headers={"location": "/a"}),
            FetchRefusal.TOO_MANY_REDIRECTS,
        ),
        (lambda r: httpx.Response(302), FetchRefusal.HTTP_STATUS),
        (lambda r: httpx.Response(404), FetchRefusal.HTTP_STATUS),
        (
            lambda r: httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"}),
            FetchRefusal.NOT_AN_IMAGE,
        ),
        (lambda r: httpx.Response(200, content=b"x"), FetchRefusal.NOT_AN_IMAGE),
        (lambda r: image(chunks(10), **{"content-encoding": "gzip"}), FetchRefusal.NOT_AN_IMAGE),
        (lambda r: image(**{"content-length": "999999999"}), FetchRefusal.TOO_LARGE),
        (lambda r: image(b"x" * 2048), FetchRefusal.TOO_LARGE),
        (lambda r: image(chunks(600, 600)), FetchRefusal.TOO_LARGE),
    ],
)
async def test_what_is_not_a_photo_within_the_limits_is_refused(make_settings, handler, refusal):
    settings = make_settings(image_max_bytes=1024)
    async with client_of(handler) as client:
        with pytest.raises(FetchError) as caught:
            await fetch_image(
                "https://photos.example/a", settings, client=client, resolver=PUBLIC_NAMES
            )
    assert caught.value.refusal is refusal


@pytest.mark.parametrize(
    ("error", "refusal"),
    [
        (httpx.ReadTimeout("slow"), FetchRefusal.TIMEOUT),
        (httpx.ConnectError("refused"), FetchRefusal.UNREACHABLE),
    ],
)
async def test_a_network_failure_is_named(flow_settings, error, refusal):
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    async with client_of(handler) as client:
        with pytest.raises(FetchError) as caught:
            await fetch_image(
                "https://photos.example/a", flow_settings, client=client, resolver=PUBLIC_NAMES
            )
    assert caught.value.refusal is refusal


async def test_the_whole_fetch_stops_at_its_time_limit(make_settings):
    settings = make_settings(image_url_timeout_seconds=0.05)

    async def slow(host: str, port: int) -> list[str]:
        await asyncio.sleep(1)
        return [PUBLIC]

    async with client_of(lambda r: image()) as client:
        with pytest.raises(FetchError) as caught:
            await fetch_image("https://photos.example/a", settings, client=client, resolver=slow)
    assert caught.value.refusal is FetchRefusal.TIMEOUT
