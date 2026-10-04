"""
quranpedia.net: its official dumps, its changes feed, and one verse at a time.

The usage policy (https://quranpedia.net/api-docs#usage-policy) asks for the
versioned dumps instead of crawling the API, the changes feed to stay current,
and at most 120 requests a minute. This client downloads two dump files,
checks each against the SHA-256 the manifest publishes, asks the changes feed
once a day, and refetches only the verses it names, one request at a time.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
from pydantic import BaseModel, ValidationError

from src.scripture.files import check_bytes, is_verified, write_atomically

log = logging.getLogger("tabsira.scripture.quranpedia")

# No personal address: the project's site is the contact the policy asks for.
USER_AGENT = "tabsira/0.1 (+https://tabsira.me)"
DUMPS_URL = "https://api.quranpedia.net/dumps"
API_URL = "https://api.quranpedia.net/v1"
SITE_URL = "https://quranpedia.net"
# «مصحف حفص نسخة نصية»: Hafs, Uthmani script in the King Fahd Complex encoding.
MUSHAF_ID = 2
MUSHAF_FILE = f"mushafs-{MUSHAF_ID}.json.gz"
SURAHS_FILE = "surahs.json.gz"
DUMP_FILES = (MUSHAF_FILE, SURAHS_FILE)
# 120 requests a minute are allowed; one every 0.6 s stays at 100.
MIN_REQUEST_INTERVAL = 0.6
REQUEST_TIMEOUT = 60.0
_REFETCH_PATH = re.compile(rf"^/v1/mushafs/{MUSHAF_ID}/(\d+)/(\d+)$")


class QuranpediaError(RuntimeError):
    """quranpedia answered with an error, or with something this client does not understand."""


class ManifestFile(BaseModel):
    name: str
    sha256: str
    bytes: int
    built_at: str


class Manifest(BaseModel):
    """The dump manifest: one version for the whole set, a SHA-256 per file."""

    version: str
    generated_at: str
    files: list[ManifestFile]

    def file(self, name: str) -> ManifestFile:
        for entry in self.files:
            if entry.name == name:
                return entry
        message = f"the dump manifest {self.version} lists no {name}"
        raise QuranpediaError(message)


class ChangedAyah(BaseModel):
    """One row of the changes feed: a verse of some mushaf corrected at `changed_at`."""

    mushaf: int
    surah: int
    ayah: int
    changed_at: str
    refetch: str


class ChangedAyahs(BaseModel):
    count: int
    truncated: bool
    rows: list[ChangedAyah]


class ChangesFeed(BaseModel):
    """What `GET /v1/changes?since=` returned for verses; other content types are not used."""

    since: str
    until: str
    ayahs: ChangedAyahs


class RefetchedAyah(BaseModel):
    """A verse as `GET /v1/mushafs/{mushaf}/{surah}/{ayah}` returns it."""

    id: int
    number: int
    surah: int
    page_number: int
    text: str


@dataclass(frozen=True)
class DumpFiles:
    """Two verified dump files of one dump version, in the download cache."""

    version: str
    mushaf: Path
    surahs: Path
    mushaf_sha256: str
    surahs_sha256: str


def new_http_client() -> httpx.AsyncClient:
    """Return the HTTP client every quranpedia request goes through."""
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


class QuranpediaClient:
    """Requests to quranpedia, spaced so the rate limit is never reached."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        interval: float = MIN_REQUEST_INTERVAL,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = http
        self._interval = interval
        self._sleep = sleep
        self._clock = clock
        self._last: float | None = None

    async def _get(self, url: str, params: dict[str, str] | None = None) -> bytes:
        if self._last is not None:
            wait = self._interval - (self._clock() - self._last)
            if wait > 0:
                await self._sleep(wait)
        self._last = self._clock()
        try:
            response = await self._http.get(url, params=params)
        except httpx.HTTPError as error:
            message = f"GET {url} failed: {type(error).__name__}"
            raise QuranpediaError(message) from error
        if response.status_code != httpx.codes.OK:
            message = f"GET {url} answered {response.status_code}"
            raise QuranpediaError(message)
        return response.content

    async def _get_model[M: BaseModel](
        self, model: type[M], url: str, params: dict[str, str] | None = None
    ) -> M:
        body = await self._get(url, params)
        try:
            return model.model_validate_json(body)
        except ValidationError as error:
            message = f"GET {url} returned an unexpected body: {error.error_count()} problems"
            raise QuranpediaError(message) from None

    async def manifest(self) -> Manifest:
        return await self._get_model(Manifest, f"{DUMPS_URL}/manifest.json")

    async def download(self, entry: ManifestFile) -> bytes:
        """Download one dump file and refuse it unless it hashes to the manifest's SHA-256."""
        data = await self._get(f"{DUMPS_URL}/{entry.name}")
        return check_bytes(data, entry.sha256, entry.name)

    async def changes(self, since: date) -> ChangesFeed:
        body = await self._get(f"{API_URL}/changes", {"since": since.isoformat()})
        try:
            raw = json.loads(body)
            return ChangesFeed.model_validate(
                {"since": raw["since"], "until": raw["until"], "ayahs": raw["changes"]["ayahs"]}
            )
        except (ValueError, TypeError, KeyError, ValidationError) as error:
            message = f"the changes feed returned an unexpected body ({type(error).__name__})"
            raise QuranpediaError(message) from None

    async def ayah(self, row: ChangedAyah) -> RefetchedAyah:
        """Refetch one changed verse of mushaf 2 by the path the feed gave for it."""
        match = _REFETCH_PATH.match(row.refetch)
        if not match or (int(match[1]), int(match[2])) != (row.surah, row.ayah):
            message = f"refusing an unexpected refetch path {row.refetch!r}"
            raise QuranpediaError(message)
        verse = await self._get_model(RefetchedAyah, f"{API_URL}{row.refetch.removeprefix('/v1')}")
        if (verse.surah, verse.number) != (row.surah, row.ayah) or not verse.text:
            message = f"{row.refetch} returned another verse or an empty text"
            raise QuranpediaError(message)
        return verse


def _dump_dir(cache_dir: Path, version: str) -> Path:
    return cache_dir / "quranpedia" / version


async def fetch_dump_files(client: QuranpediaClient, cache_dir: Path) -> DumpFiles:
    """
    Make sure the current dump's two files are in the cache, verified; download what is missing.

    The manifest is saved beside them, so a later run can check them again
    without asking quranpedia.
    """
    manifest = await client.manifest()
    folder = _dump_dir(cache_dir, manifest.version)
    for name in DUMP_FILES:
        entry = manifest.file(name)
        path = folder / name
        if is_verified(path, entry.sha256):
            log.info("quranpedia %s %s already verified", manifest.version, name)
            continue
        write_atomically(path, await client.download(entry))
        log.info("quranpedia %s %s downloaded and verified", manifest.version, name)
    write_atomically(folder / "manifest.json", manifest.model_dump_json(indent=1).encode())
    return _dump_files(folder, manifest)


def _dump_files(folder: Path, manifest: Manifest) -> DumpFiles:
    return DumpFiles(
        version=manifest.version,
        mushaf=folder / MUSHAF_FILE,
        surahs=folder / SURAHS_FILE,
        mushaf_sha256=manifest.file(MUSHAF_FILE).sha256,
        surahs_sha256=manifest.file(SURAHS_FILE).sha256,
    )


def cached_dump_files(cache_dir: Path, version: str | None = None) -> DumpFiles | None:
    """
    Return the newest dump in the cache whose files still match its manifest, or None.

    With `version`, only that dump is considered.
    """
    root = cache_dir / "quranpedia"
    folders = [_dump_dir(cache_dir, version)] if version else sorted(root.glob("*"), reverse=True)
    for folder in folders:
        manifest_path = folder / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = Manifest.model_validate_json(manifest_path.read_bytes())
        if all(is_verified(folder / name, manifest.file(name).sha256) for name in DUMP_FILES):
            return _dump_files(folder, manifest)
    return None


def dump_url(name: str) -> str:
    """Return the public address of one dump file."""
    return f"{DUMPS_URL}/{name}"
