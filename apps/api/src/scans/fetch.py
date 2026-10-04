"""
Fetch a photo given by its address, without letting the address reach inside our network.

v2 §6: public addresses only, default ports, at most three redirects, 12
seconds, 15 MB, `image/*`. Every hop is checked before it is requested: the
scheme is http or https, the port is the scheme's default, and every address
the name resolves to is a public one. The connection itself is then made by a
network backend that resolves the name again and connects only to an address
it has just checked, so a name that answers a public address to the check and
a private one to the connection (DNS rebinding) still cannot reach inside. No
cookie, credential or header of the caller is forwarded. The bytes are read as
a stream and the fetch stops as soon as they pass the limit.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Iterable
from enum import StrEnum
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx

from src.config import Settings

USER_AGENT = "tabsira/0.1 (+https://tabsira.me)"
DEFAULT_PORTS = {"http": 80, "https": 443}
REDIRECTS = frozenset({301, 302, 303, 307, 308})
MAX_URL_LENGTH = 2048

Resolver = Callable[[str, int], Awaitable[list[str]]]


class FetchRefusal(StrEnum):
    """Why a photo address was refused or could not be fetched. Stable codes."""

    INVALID_URL = "invalid_url"
    FORBIDDEN_ADDRESS = "forbidden_address"
    TOO_MANY_REDIRECTS = "too_many_redirects"
    TIMEOUT = "timeout"
    UNREACHABLE = "unreachable"
    HTTP_STATUS = "http_status"
    NOT_AN_IMAGE = "not_an_image"
    TOO_LARGE = "too_large"


class FetchError(Exception):
    def __init__(self, refusal: FetchRefusal, detail: str) -> None:
        super().__init__(f"{refusal.value}: {detail}")
        self.refusal = refusal
        self.detail = detail


async def system_resolver(host: str, port: int) -> list[str]:
    """Resolve a host name to every address it has, as text."""
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
    )
    return sorted({str(info[4][0]) for info in infos})


def is_public(address: str) -> bool:
    """Tell whether an address is globally routable unicast (an IPv4-mapped one is unwrapped)."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast and not ip.is_reserved


def check_url(url: str) -> tuple[str, int]:
    """Return the host and port of an address that may be fetched, or raise FetchError."""
    if len(url) > MAX_URL_LENGTH:
        raise FetchError(FetchRefusal.INVALID_URL, "the address is too long")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise FetchError(FetchRefusal.INVALID_URL, "the address does not parse") from None
    if parts.scheme not in DEFAULT_PORTS or not parts.hostname:
        raise FetchError(FetchRefusal.INVALID_URL, "only http and https addresses with a host")
    if parts.username or parts.password:
        raise FetchError(FetchRefusal.INVALID_URL, "an address with credentials")
    default = DEFAULT_PORTS[parts.scheme]
    if port is not None and port != default:
        raise FetchError(FetchRefusal.FORBIDDEN_ADDRESS, f"port {port} is not {default}")
    return parts.hostname, default


async def check_addresses(host: str, port: int, resolver: Resolver) -> list[str]:
    """Resolve `host` and return its addresses when every one is public, or raise FetchError."""
    try:
        addresses = await resolver(host, port)
    except OSError:
        raise FetchError(FetchRefusal.UNREACHABLE, "the name does not resolve") from None
    if not addresses:
        raise FetchError(FetchRefusal.UNREACHABLE, "the name has no address")
    if not all(is_public(address) for address in addresses):
        raise FetchError(FetchRefusal.FORBIDDEN_ADDRESS, "the name points at a non-public address")
    return addresses


class PublicOnlyBackend(httpcore.AsyncNetworkBackend):
    """A network backend that connects only to public addresses it has just resolved and checked."""

    def __init__(self, resolver: Resolver = system_resolver) -> None:
        self._resolver = resolver
        self._backend = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore's interface
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            addresses = await check_addresses(host, port, self._resolver)
        except FetchError as refusal:
            raise httpcore.ConnectError(str(refusal)) from None
        return await self._backend.connect_tcp(
            addresses[0], port, timeout, local_address, socket_options
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore's interface
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        message = "unix sockets are never used to fetch a photo"
        raise httpcore.ConnectError(message)

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class PublicOnlyTransport(httpx.AsyncHTTPTransport):
    """httpx's transport, its connection pool built on `PublicOnlyBackend`."""

    def __init__(self, resolver: Resolver = system_resolver) -> None:
        super().__init__(retries=0, trust_env=False)
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(),
            max_connections=4,
            max_keepalive_connections=0,
            network_backend=PublicOnlyBackend(resolver),
        )


def fetch_client(settings: Settings, resolver: Resolver = system_resolver) -> httpx.AsyncClient:
    """Return an HTTP client for photo addresses: no redirects of its own, no proxy from the environment."""
    return httpx.AsyncClient(
        transport=PublicOnlyTransport(resolver),
        follow_redirects=False,
        trust_env=False,
        timeout=httpx.Timeout(settings.image_url_timeout_seconds),
        # No compression: a small compressed body must not expand past the size limit.
        headers={"User-Agent": USER_AGENT, "Accept": "image/*", "Accept-Encoding": "identity"},
    )


async def fetch_image(
    url: str,
    settings: Settings,
    *,
    client: httpx.AsyncClient,
    resolver: Resolver = system_resolver,
) -> bytes:
    """Return the bytes of the photo at `url`, or raise FetchError naming the refusal."""
    try:
        async with asyncio.timeout(settings.image_url_timeout_seconds):
            return await _follow(url, settings, client, resolver)
    except TimeoutError:
        raise FetchError(FetchRefusal.TIMEOUT, "the photo did not arrive in time") from None


async def _follow(
    url: str, settings: Settings, client: httpx.AsyncClient, resolver: Resolver
) -> bytes:
    current = url.strip()
    for _hop in range(settings.image_url_max_redirects + 1):
        host, port = check_url(current)
        await check_addresses(host, port, resolver)
        try:
            async with client.stream("GET", current) as response:
                if response.status_code in REDIRECTS:
                    location = response.headers.get("location")
                    if not location:
                        raise FetchError(FetchRefusal.HTTP_STATUS, "a redirect without a location")
                    current = urljoin(current, location)
                    continue
                return await _read_image(response, settings.image_max_bytes)
        except httpx.TimeoutException:
            raise FetchError(FetchRefusal.TIMEOUT, "the photo did not arrive in time") from None
        except httpx.HTTPError as error:
            raise FetchError(FetchRefusal.UNREACHABLE, type(error).__name__) from None
    raise FetchError(
        FetchRefusal.TOO_MANY_REDIRECTS, f"more than {settings.image_url_max_redirects} redirects"
    )


async def _read_image(response: httpx.Response, max_bytes: int) -> bytes:
    if response.status_code != httpx.codes.OK:
        raise FetchError(FetchRefusal.HTTP_STATUS, f"HTTP {response.status_code}")
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not content_type.startswith("image/"):
        raise FetchError(FetchRefusal.NOT_AN_IMAGE, f"content type {content_type or 'missing'}")
    encoding = response.headers.get("content-encoding", "identity").strip().lower()
    if encoding not in {"", "identity"}:
        # Asked for none: a compressed body could expand far past the limit once decoded.
        raise FetchError(FetchRefusal.NOT_AN_IMAGE, f"content encoding {encoding}")
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > max_bytes:
        raise FetchError(FetchRefusal.TOO_LARGE, f"{declared} bytes announced")
    received = bytearray()
    async for chunk in response.aiter_bytes():
        received += chunk
        if len(received) > max_bytes:
            raise FetchError(FetchRefusal.TOO_LARGE, f"more than {max_bytes} bytes")
    return bytes(received)
