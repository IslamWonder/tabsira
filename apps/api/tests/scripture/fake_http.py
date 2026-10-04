"""A fake quranpedia for the tests: canned answers by URL path, every request recorded."""

from __future__ import annotations

import gzip
import json
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import httpx

from src.scripture.files import bytes_sha256
from src.scripture.hadith import CollectionSource
from src.scripture.quranpedia import QuranpediaClient
from tests.scripture.fixtures import HADITH_FIXTURES, fixture_path, fixture_sources

Answer = httpx.Response | Callable[[httpx.Request], httpx.Response]


def gz_fixture(name: str) -> bytes:
    """A fixture compressed the way quranpedia serves its dumps."""
    return gzip.compress(fixture_path(name).read_bytes(), mtime=0)


def manifest_for(files: dict[str, bytes], version: str = "2026-10-03") -> dict[str, Any]:
    return {
        "version": version,
        "generated_at": f"{version}T06:00:47+00:00",
        "files": [
            {
                "name": name,
                "sha256": bytes_sha256(data),
                "bytes": len(data),
                "built_at": f"{version}T06:00:02+00:00",
            }
            for name, data in files.items()
        ],
    }


class FakeQuranpedia:
    """Serve `routes` (path, or path?query) and remember every request made."""

    def __init__(self, routes: dict[str, Answer]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = request.url.path + (f"?{request.url.query.decode()}" if request.url.query else "")
        answer = self.routes.get(key) or self.routes.get(request.url.path)
        if answer is None:
            return httpx.Response(404, json={"error": "not found"})
        return answer(request) if callable(answer) else answer

    def client(self) -> QuranpediaClient:
        http = httpx.AsyncClient(transport=httpx.MockTransport(self.handler))

        async def no_wait(_seconds: float) -> None:
            return None

        return QuranpediaClient(http, sleep=no_wait)


def dump_routes(version: str = "2026-10-03") -> dict[str, Answer]:
    """Routes that serve the manifest and the two dump files built from the fixtures."""
    files = {
        "mushafs-2.json.gz": gz_fixture("quranpedia-mushafs-2.json"),
        "surahs.json.gz": gz_fixture("quranpedia-surahs.json"),
    }
    routes: dict[str, Answer] = {
        "/dumps/manifest.json": httpx.Response(200, json=manifest_for(files, version)),
    }
    for name, data in files.items():
        routes[f"/dumps/{name}"] = httpx.Response(200, content=data)
    return routes


def json_response(payload: Any) -> httpx.Response:
    return httpx.Response(200, content=json.dumps(payload, ensure_ascii=False).encode())


def hadith_routes(sources: tuple[CollectionSource, ...] | None = None) -> dict[str, Answer]:
    """Routes that serve each fixture hadith file at the path of its pinned URL."""
    return {
        urlsplit(source.url).path: httpx.Response(
            200, content=fixture_path(HADITH_FIXTURES[source.slug]).read_bytes()
        )
        for source in sources or fixture_sources()
    }
