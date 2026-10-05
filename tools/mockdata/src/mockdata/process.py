"""
`python -m mockdata.process`: task 23.4, the real pipeline over the placepix photos, then the texts.

    make mock-photos     # photos -> photo-library.json (stops at 150 photos with an insight)
    make mock-data       # the generator builds the members' activity from those photos
    make mock-texts      # reflections and comments -> texts-library.json and the final file

The photo stage takes the kept placepix catalogue in id order and runs every photo the photo
library does not hold yet through the scan pipeline of apps/api (`mockdata.scan`), many at
once, and stops as soon as the library holds `--stop-at` photos with an insight: the photos
not reached stay unprocessed, not dropped. Each finished photo is written to the library at
once with its outcome, its provider and model, its cost and, when it gave one, the insight in
the importer's shape; a photo that failed in a way another run may fix is left out of it. When
the provider answers 429 or 5xx, fewer photos run at once from then on; when it fails several
photos in a row, the rest goes to the fallback provider. The run is recorded in the library.

`photos --add-hadith` runs the kept photos whose insight has no hadith through the same scan
again, as a member's scan does now that a hadith shows without a ruling (decision 65). A photo
takes the new insight whole when it is kept and carries a hadith, so the verse, the hadith and
the words written about them come from one run; otherwise it keeps its insight. Its outcome
stays, its cost grows by the new calls, and the posts' texts written before the new insight
are written again by the next texts stage.

The texts stage reads the generated file, writes one post at a time through the composer model
(`mockdata.voices`), keeps what passes the guards in the texts library, and fills the file
from it. Before the file is replaced, the importer's own checks run over it against the
development database, read only: its shape, the scripture guard over every text, and every
evidence id present in the store. `process-report.json` says what was kept and dropped and
why, the providers and models, the time, the tokens and the cost of both stages, and how many
distinct verses and hadiths the file uses.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
import time
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from src.ai.client import (
    ChatResult,
    EmbeddingResult,
    ModelClient,
    ModelImage,
    ModerationResult,
    client_for,
)
from src.ai.errors import AiCallError, AiErrorCode
from src.ai.records import CallLog, CallRecord
from src.cli import import_mock
from src.cli.import_mock import (
    MockImportError,
    check_member_texts,
    check_scripture_guard,
    parse,
)
from src.config import (
    AiProvider,
    AiStage,
    ProviderSettings,
    RerankerKind,
    Settings,
    load_settings,
)
from src.database import dispose_engine, get_engine
from src.pipeline.detector import DetectorClient
from src.pipeline.insight.engine import build_engine
from src.pipeline.schemas import DetectorRequest, DetectorResult
from src.scans.accept import leaks
from src.services.moderation_guard import GuardVerdict, OpenAiTextGuard

from mockdata import catalogue, library
from mockdata.catalogue import Photo
from mockdata.cli import DATA_DIR, OUT_NAME, fetch_photos
from mockdata.library import KEPT, Library, dumps, kept_photos, outcome_of, text_key
from mockdata.scan import ScanResult, ScanTools, rolled_back, run_scan
from mockdata.scenes import describe
from mockdata.voices import (
    SPONSOR,
    Brief,
    Check,
    Slot,
    Voices,
    accept_texts,
    ask,
    brief_of,
    cleaned,
    text_model,
    verdict_reason,
)

REPORT_NAME = "process-report.json"
STATE_NAME = "process-state.json"
CATALOGUE_NAME = "placepix-catalogue.json"
PARALLEL = 20
STOP_AT = 150
ATTEMPTS = 3
BACKOFF_SECONDS = 10.0
# Photos in a row the primary provider failed before the rest goes to the fallback.
FALLBACK_AFTER = 8
# Answers that say the provider is overloaded: fewer photos run at once after one of them.
THROTTLED = frozenset({AiErrorCode.RATE_LIMITED, AiErrorCode.SERVER_ERROR})
# The guard of member text answers «guard_unavailable» when it could not be asked.
GUARD_UNAVAILABLE = "guard_unavailable"
HTTP_TIMEOUT_SECONDS = 120.0
DOWNLOAD_TIMEOUT_SECONDS = 30.0
MAX_PHOTO_BYTES = 15 * 1024 * 1024
# Outcomes of a photo that say a provider is failing.
VISION_TROUBLE = frozenset({"vision_failed", "model_unavailable"})


class DownloadError(Exception):
    """The photo could not be fetched; the message is a short code."""


def now_text() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _say(line: str) -> None:
    sys.stdout.write(f"{line}\n")
    sys.stdout.flush()


# ─── Bounding the calls ───


class Throttled(ModelClient):
    """A client whose calls wait for a shared gate, so the whole run makes few calls at once."""

    def __init__(self, inner: ModelClient, gate: asyncio.Semaphore) -> None:
        self._inner = inner
        self._gate = gate

    @property
    def provider(self) -> AiProvider:
        return self._inner.provider

    @property
    def settings(self) -> ProviderSettings:
        return self._inner.settings

    async def chat_json[T: BaseModel](
        self,
        schema: type[T],
        *,
        stage: AiStage,
        system: str,
        user: str,
        images: Sequence[ModelImage] = (),
        model: str | None = None,
        max_output_tokens: int = 4096,
        temperature: float | None = None,
        reasoning_effort: str | None = None,
    ) -> ChatResult[T]:
        async with self._gate:
            return await self._inner.chat_json(
                schema,
                stage=stage,
                system=system,
                user=user,
                images=images,
                model=model,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
            )

    async def embed(
        self, texts: Sequence[str], *, model: str | None = None, dimensions: int | None = None
    ) -> EmbeddingResult:
        async with self._gate:
            return await self._inner.embed(texts, model=model, dimensions=dimensions)

    async def moderate_image(
        self, image: ModelImage, *, model: str | None = None
    ) -> ModerationResult:
        async with self._gate:
            return await self._inner.moderate_image(image, model=model)

    async def moderate_text(self, text: str, *, model: str | None = None) -> ModerationResult:
        async with self._gate:
            return await self._inner.moderate_text(text, model=model)


DETECTOR_PARALLEL = 6


class CappedDetector(DetectorClient):
    """The local detector runs on a CPU: it takes fewer calls at once than the model endpoints."""

    def __init__(self, *args: Any, limit: int = DETECTOR_PARALLEL, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._limit = asyncio.Semaphore(limit)

    async def detect(self, request: DetectorRequest) -> DetectorResult:
        async with self._limit:
            return await super().detect(request)


class AdaptiveGate:
    """How many photos or posts run at once; halved, never below one, when the provider is busy."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.active = 0
        self.events: list[dict[str, Any]] = []
        self._changed = asyncio.Condition()

    @contextlib.asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        async with self._changed:
            await self._changed.wait_for(lambda: self.active < self.limit)
            self.active += 1
        try:
            yield
        finally:
            async with self._changed:
                self.active -= 1
                self._changed.notify_all()

    def observe(self, calls: Sequence[CallRecord]) -> None:
        """Lower the limit when a call met a 429 or a 5xx, even one a retry got past."""
        codes = {c.error_code for c in calls} | {code for c in calls for code in c.retried_errors}
        busy = sorted(code.value for code in codes if code in THROTTLED)
        if busy and self.limit > 1:
            self.limit = max(1, self.limit // 2)
            self.events.append({"at": now_text(), "limit": self.limit, "codes": busy})
            _say(f"provider busy ({', '.join(busy)}): {self.limit} at once from now on")


def usage_of(calls: Sequence[CallRecord]) -> dict[str, dict[str, Any]]:
    """Tokens and cost of some calls, by `provider/model`; never what was asked or answered."""
    usage: dict[str, dict[str, Any]] = {}
    for call in calls:
        row = usage.setdefault(
            f"{call.provider.value}/{call.model}",
            {"calls": 0, "failed": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
        )
        row["calls"] += 1
        row["failed"] += 0 if call.ok else 1
        row["input_tokens"] += call.usage.input_tokens
        row["output_tokens"] += call.usage.output_tokens
        row["cost_usd"] = round(row["cost_usd"] + (call.cost_usd or 0.0), 6)
    return usage


def merge_usage(rows: Sequence[dict[str, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    total: dict[str, dict[str, Any]] = {}
    for usage in rows:
        for key, row in usage.items():
            into = total.setdefault(key, dict.fromkeys(row, 0))
            for name, value in row.items():
                into[name] = round(into[name] + value, 6)
    return dict(sorted(total.items()))


def cost_of(usage: dict[str, dict[str, Any]]) -> float:
    return round(float(sum(row["cost_usd"] for row in usage.values())), 6)


# ─── The services a run calls ───


@dataclass(frozen=True)
class Services:
    """What a run calls outside itself: built from the settings, or by a test."""

    download: Callable[[str], Awaitable[bytes]]
    scan: Callable[[bytes, str, AiProvider], Awaitable[ScanResult]]
    voices: Callable[[Brief], Awaitable[tuple[Voices, CallRecord]]]
    check: Check
    validate: Callable[[bytes], Awaitable[list[str]]]
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep


# ─── The photo stage ───


@dataclass
class Switch:
    """Which provider runs the next photo, and when the primary is failing too often."""

    primary: AiProvider
    fallback: AiProvider | None
    current: AiProvider = field(init=False)
    streak: int = 0
    switched_after: int | None = None

    def __post_init__(self) -> None:
        self.current = self.primary

    def observe(self, provider: AiProvider, outcome: str, done: int) -> None:
        if provider is not self.current or self.current is not self.primary:
            return
        self.streak = self.streak + 1 if outcome in VISION_TROUBLE else 0
        if self.fallback is not None and self.streak >= FALLBACK_AFTER:
            self.current = self.fallback
            self.switched_after = done


@dataclass(frozen=True)
class PhotoOptions:
    folder: Path = DATA_DIR
    stop_at: int | None = STOP_AT
    parallel: int = PARALLEL
    limit: int | None = None
    reprocess: bool = False
    fallback: AiProvider | None = AiProvider.OPENAI
    add_hadith: bool = False


def is_retry(result: ScanResult) -> bool:
    """A photo another run may finish: a provider or the store did not answer, or no photo."""
    return result.transient or result.outcome == "download_failed"


async def scan_photo(
    photo: Photo, services: Services, switch: Switch, done: Callable[[], int]
) -> tuple[ScanResult, AiProvider, int, list[CallRecord]]:
    """Download and scan one photo, retrying what may pass later."""
    result = ScanResult("download_failed")
    provider = switch.current
    calls: list[CallRecord] = []
    attempt = 0
    for attempt in range(1, ATTEMPTS + 1):  # pragma: no branch - the loop ends by break or last try
        provider = switch.current
        try:
            data = await services.download(photo.url)
        except DownloadError as error:
            result = ScanResult("download_failed", detail=str(error))
        else:
            result = await services.scan(data, f"mock-{photo.id}", provider)
            calls += result.calls
            switch.observe(provider, result.outcome, done())
        if not is_retry(result):
            break
        if attempt < ATTEMPTS:
            await services.sleep(BACKOFF_SECONDS * 2 ** (attempt - 1))
    return result, provider, attempt, calls


def photo_entry(
    photo: Photo,
    result: ScanResult,
    provider: AiProvider,
    attempts: int,
    calls: Sequence[CallRecord],
    settings: Settings,
    processed_at: str,
) -> dict[str, Any]:
    """The library's entry of a finished photo."""
    usage = usage_of(calls)
    block = settings.ai_ovh if provider is AiProvider.OVH else settings.ai_openai
    return {
        "url": photo.url,
        "filename": photo.filename,
        "category": photo.category,
        "width": photo.width,
        "height": photo.height,
        "scene": describe(photo.filename, photo.category).model_dump(),
        "outcome": outcome_of(result.outcome),
        "pipeline_outcome": result.outcome,
        "detail": result.detail,
        "provider": provider.value,
        "model": block.vision_model,
        "detector": result.detector,
        "attempts": attempts,
        "usage": usage,
        "cost_usd": cost_of(usage),
        "processed_at": processed_at,
        "insight": result.body if result.outcome == KEPT else None,
        "insight_at": processed_at,
    }


def candidates(folder: Path) -> list[Photo]:
    """The kept placepix photos, in id order, from the generator's catalogue cache."""
    return catalogue.filter_photos(
        catalogue.get_catalogue(folder / CATALOGUE_NAME, False, fetch_photos)
    )


def adopt_state(
    state_path: Path, photos: Library, by_id: dict[int, Photo], settings: Settings
) -> int:
    """
    Add the finished photos of an earlier run's `process-state.json` the library lacks.

    That run kept its results there before the library existed; its calls are kept as usage,
    so a photo is never paid for twice. Its time is the state file's.
    """
    if not state_path.exists():
        return 0
    state = json.loads(state_path.read_text(encoding="utf-8"))
    at = datetime.fromtimestamp(state_path.stat().st_mtime, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    added = 0
    for pid, old in state.get("images", {}).items():
        photo = by_id.get(int(pid))
        if photo is None or pid in photos.entries or old.get("retry"):
            continue
        result = ScanResult(
            old["outcome"], body=old["insight"], detail=old["detail"], detector=old["detector"]
        )
        provider = AiProvider(old["provider"])
        entry = photo_entry(photo, result, provider, old["attempts"], [], settings, at)
        entry["usage"] = old["usage"]
        entry["cost_usd"] = cost_of(old["usage"])
        photos.entries[pid] = entry
        added += 1
    return added


async def photo_stage(options: PhotoOptions, settings: Settings, services: Services) -> int:
    """Run the photos the library lacks until it holds `stop_at` with an insight."""
    started, wall = now_text(), time.monotonic()
    photos = library.photos(options.folder / library.PHOTOS_NAME)
    every = candidates(options.folder)
    adopted = adopt_state(options.folder / STATE_NAME, photos, {p.id: p for p in every}, settings)
    await photos.save()
    pending = [p for p in every if options.reprocess or str(p.id) not in photos.entries]
    if options.limit is not None:
        pending = pending[: options.limit]
    fallback = options.fallback if options.fallback is not settings.ai_provider else None
    switch = Switch(settings.ai_provider, fallback)
    gate = AdaptiveGate(options.parallel)
    counts: Counter[str] = Counter()
    tasks: list[asyncio.Task[None]] = []

    def enough() -> bool:
        return options.stop_at is not None and len(kept_photos(photos)) >= options.stop_at

    async def one(photo: Photo) -> None:
        async with gate.slot():
            if enough():
                return
            result, provider, attempts, calls = await scan_photo(
                photo, services, switch, lambda: len(photos.entries)
            )
        gate.observe(calls)
        counts[result.outcome] += 1
        if is_retry(result):
            _say(f"photo {photo.id}: {result.outcome}, left for the next run")
            return
        entry = photo_entry(photo, result, provider, attempts, calls, settings, now_text())
        await photos.put(str(photo.id), entry)
        _say(f"photo {photo.id}: {entry['outcome']} ({provider.value})")
        if enough():
            # The photos still running are stopped: they stay unprocessed, not dropped.
            for task in tasks:
                if task is not asyncio.current_task():
                    task.cancel()

    tasks += [asyncio.create_task(one(photo)) for photo in pending]
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        photos.runs.append(
            {
                "stage": "photos",
                "started_at": started,
                "seconds": round(time.monotonic() - wall, 1),
                "provider": settings.ai_provider.value,
                "parallel": options.parallel,
                "throttled": gate.events,
                "fallback": (
                    {"to": switch.current.value, "after_photos": switch.switched_after}
                    if switch.switched_after is not None
                    else None
                ),
                "adopted_from_state": adopted,
                "outcomes": dict(sorted(counts.items())),
            }
        )
        await photos.save()
    kept = len(kept_photos(photos))
    _say(f"{photos.path}: {len(photos.entries)} photos, {kept} with an insight")
    return 0


def without_hadith(photos: Library) -> list[int]:
    """The kept photos whose insight carries no hadith, in id order."""
    return [pid for pid, entry in kept_photos(photos).items() if not entry["insight"]["hadith"]]


def with_new_insight(
    entry: dict[str, Any], result: ScanResult, calls: Sequence[CallRecord], at: str
) -> tuple[dict[str, Any], str]:
    """
    Merge a new run of a kept photo into its entry and say what became of it.

    The new insight is taken whole, never its hadith alone: the composer wrote the insight's
    words for the verse and the hadith the gate paired.
    """
    usage = merge_usage([entry["usage"], usage_of(calls)])
    merged = entry | {"usage": usage, "cost_usd": cost_of(usage)}
    if result.outcome != KEPT or result.body is None:
        return merged, f"kept_old:{result.outcome}"
    if not result.body["hadith"]:
        return merged, "kept_old:no_hadith"
    return merged | {"insight": result.body, "insight_at": at}, "hadith_added"


async def hadith_stage(options: PhotoOptions, settings: Settings, services: Services) -> int:
    """Run the kept photos without a hadith again and take a new insight that carries one."""
    started, wall = now_text(), time.monotonic()
    photos = library.photos(options.folder / library.PHOTOS_NAME)
    by_id = {p.id: p for p in candidates(options.folder)}
    pending = [pid for pid in without_hadith(photos) if pid in by_id]
    if options.limit is not None:
        pending = pending[: options.limit]
    switch = Switch(settings.ai_provider, None)
    gate = AdaptiveGate(options.parallel)
    counts: Counter[str] = Counter()

    async def one(pid: int) -> None:
        async with gate.slot():
            result, _, _, calls = await scan_photo(
                by_id[pid], services, switch, lambda: len(photos.entries)
            )
        gate.observe(calls)
        entry, what = with_new_insight(photos.entries[str(pid)], result, calls, now_text())
        counts["retry" if is_retry(result) else what] += 1
        await photos.put(str(pid), entry)
        _say(f"photo {pid}: {what}")

    try:
        await asyncio.gather(*(one(pid) for pid in pending), return_exceptions=True)
    finally:
        photos.runs.append(
            {
                "stage": "hadith",
                "started_at": started,
                "seconds": round(time.monotonic() - wall, 1),
                "provider": settings.ai_provider.value,
                "parallel": options.parallel,
                "throttled": gate.events,
                "photos": len(pending),
                "outcomes": dict(sorted(counts.items())),
            }
        )
        await photos.save()
    left = len(without_hadith(photos))
    _say(
        f"{photos.path}: {len(kept_photos(photos)) - left} kept photos with a hadith, {left} without"
    )
    return 0


# ─── The texts stage ───


@dataclass(frozen=True)
class TextOptions:
    file: Path = DATA_DIR / OUT_NAME
    parallel: int = PARALLEL
    limit: int | None = None


def signature(slots: Sequence[Slot]) -> list[list[str | None]]:
    return [[slot.ref, slot.parent] for slot in slots]


def post_briefs(document: dict[str, Any]) -> list[tuple[Brief, int]]:
    """
    Every post of an insight whose photo has one, with its comment slots and its photo id.

    Then the sponsor's note of every sponsored atlas entry, a brief of its own (`sponsor:<insight>`).
    """
    countries = {member["ref"]: member["country"] for member in document["members"]}
    insights = {item["ref"]: item for item in document["insights"]}
    bodies = {image["placepix_id"]: image["insight"] for image in document["images"]}
    slots: dict[str, list[Slot]] = {}
    for comment in document["comments"]:
        slots.setdefault(comment["post"], []).append(
            Slot(comment["ref"], comment["parent"], countries.get(comment["member"], ""))
        )
    found = []
    for post in document["posts"]:
        item = insights.get(post["insight"])
        body = bodies.get(item["image"]) if item else None
        if item is None or body is None:
            continue
        brief = brief_of(
            post["ref"], body, countries.get(item["member"], ""), slots.get(post["ref"], [])
        )
        found.append((brief, item["image"]))
    for entry in document["map_entries"]:
        sponsor = entry.get("sponsor")
        item = insights.get(entry["insight"])
        body = bodies.get(item["image"]) if item else None
        if sponsor is None or item is None or body is None:
            continue
        brief = brief_of(
            f"sponsor:{entry['insight']}", body, countries.get(sponsor["member"], ""), [], SPONSOR
        )
        found.append((brief, item["image"]))
    return found


def reusable(entry: dict[str, Any] | None, brief: Brief, insight_at: str = "") -> bool:
    """A library entry still fits the post: written after its insight, for the same slots."""
    return (
        entry is not None
        and not entry.get("retry", False)
        and entry["slots"] == signature(brief.slots)
        and entry.get("written_at", "") >= insight_at
    )


def insight_times(photos: Library) -> dict[int, str]:
    """When each kept photo's insight was made; the texts written before it are rewritten."""
    return {
        pid: entry.get("insight_at") or entry.get("processed_at", "")
        for pid, entry in kept_photos(photos).items()
    }


async def write_post(brief: Brief, services: Services) -> tuple[dict[str, Any], list[CallRecord]]:
    """Ask for one post's texts, retrying a failed call; keep only what passes every check."""
    calls: list[CallRecord] = []
    for attempt in range(1, ATTEMPTS + 1):  # pragma: no branch - the loop ends by return
        try:
            voices, record = await services.voices(brief)
        except AiCallError as error:
            if error.record is not None:
                calls.append(error.record)
            if attempt == ATTEMPTS:
                failed = {"retry": True, "error": error.code.value, "usage": usage_of(calls)}
                return failed, calls
            await services.sleep(BACKOFF_SECONDS * 2 ** (attempt - 1))
            continue
        calls.append(record)
        written = await accept_texts(brief, voices, services.check)
        entry = {
            "reflection": written.reflection,
            "comments": written.comments,
            "dropped": written.dropped,
            "usage": usage_of(calls),
        }
        return entry, calls
    raise AssertionError  # pragma: no cover - the loop returns on its last attempt


def assemble(document: dict[str, Any], texts: Library, briefs: Sequence[tuple[Brief, int]]) -> None:
    """Fill the posts' reflections and the comments' texts from the texts library."""
    written = {
        brief.post: texts.entries.get(text_key(brief.post, pid), {}) for brief, pid in briefs
    }
    for post in document["posts"]:
        # The author may have written none: the library keeps the text, the post leaves it out.
        text = written.get(post["ref"], {}).get("reflection")
        post["reflection"] = text if post.get("reflect", True) else None
    for entry in document["map_entries"]:
        if entry.get("sponsor") is not None:
            kept = written.get(f"sponsor:{entry['insight']}", {})
            entry["sponsor"]["reflection"] = kept.get("reflection")
    for comment in document["comments"]:
        texts_of = written.get(comment["post"], {}).get("comments", {})
        comment["text"] = texts_of.get(comment["ref"])


async def texts_stage(options: TextOptions, settings: Settings, services: Services) -> int:
    """Write the posts' texts the library lacks, fill the file, check it, then replace it."""
    started, wall = now_text(), time.monotonic()
    folder = options.file.parent
    texts = library.texts(folder / library.TEXTS_NAME)
    document = json.loads(options.file.read_text(encoding="utf-8"))
    briefs = post_briefs(document)
    made = insight_times(library.photos(folder / library.PHOTOS_NAME))
    pending = [
        (brief, pid)
        for brief, pid in briefs
        if not reusable(texts.entries.get(text_key(brief.post, pid)), brief, made.get(pid, ""))
    ]
    if options.limit is not None:
        pending = pending[: options.limit]
    gate = AdaptiveGate(options.parallel)

    async def one(brief: Brief, pid: int) -> None:
        async with gate.slot():
            entry, calls = await write_post(brief, services)
        gate.observe(calls)
        entry |= {"slots": signature(brief.slots), "written_at": now_text()}
        await texts.put(text_key(brief.post, pid), entry)
        _say(f"post {brief.post}: {'failed' if entry.get('retry') else 'written'}")

    try:
        await asyncio.gather(*(one(brief, pid) for brief, pid in pending))
    finally:
        texts.runs.append(
            {
                "stage": "texts",
                "started_at": started,
                "seconds": round(time.monotonic() - wall, 1),
                "parallel": options.parallel,
                "throttled": gate.events,
                "written": len(pending),
            }
        )
        await texts.save()
    assemble(document, texts, briefs)
    text = dumps(document) + "\n"
    problems = await services.validate(text.encode("utf-8"))
    photos = library.photos(folder / library.PHOTOS_NAME)
    summary = report(document, photos, texts, briefs, settings, problems)
    library.write_atomically(
        folder / REPORT_NAME, json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    if problems:
        for line in problems:
            _say(f"check failed: {line}")
        _say(f"{options.file} was not written")
        return 1
    library.write_atomically(options.file, text)
    _say(f"{options.file}: written; report in {folder / REPORT_NAME}")
    return 0


# ─── The report ───


def evidence_counts(document: dict[str, Any]) -> dict[str, int]:
    bodies = [image["insight"] for image in document["images"] if image["insight"]]
    verses = {(b["quran"]["surah"], b["quran"]["ayah"]) for b in bodies if b["quran"]}
    hadiths = {(b["hadith"]["collection"], b["hadith"]["number"]) for b in bodies if b["hadith"]}
    return {
        "distinct_verses": len(verses),
        "distinct_hadiths": len(hadiths),
        "photos_with_verse": sum(1 for b in bodies if b["quran"]),
        "photos_with_hadith": sum(1 for b in bodies if b["hadith"]),
    }


def report(
    document: dict[str, Any],
    photos: Library,
    texts: Library,
    briefs: Sequence[tuple[Brief, int]],
    settings: Settings,
    problems: list[str],
) -> dict[str, Any]:
    entries = list(photos.entries.values())
    outcomes = Counter(entry["outcome"] for entry in entries)
    errors = Counter(entry["pipeline_outcome"] for entry in entries if entry["outcome"] == "error")
    used = [texts.entries.get(text_key(b.post, pid), {}) for b, pid in briefs]
    dropped: Counter[str] = Counter()
    for entry in used:
        dropped.update(entry.get("dropped", {}))
    photo_usage = merge_usage([entry["usage"] for entry in entries])
    text_usage = merge_usage([entry["usage"] for entry in texts.entries.values()])
    runs = photos.runs + texts.runs
    images_used = {image["placepix_id"] for image in document["images"] if image["insight"]}
    return {
        "file": OUT_NAME,
        "version": document["version"],
        "generated_at": now_text(),
        "runs": runs,
        "duration_seconds": round(sum(run["seconds"] for run in runs), 1),
        "provider": settings.ai_provider.value,
        "providers_used": dict(Counter(entry["provider"] for entry in entries)),
        "models": {
            "vision": settings.ai.vision_model,
            "planner": settings.ai.planner_model,
            "verify": settings.ai.verify_model,
            "compose": settings.ai.compose_model,
            "embedding": settings.ai.embedding_model,
            "rerank": "off" if settings.reranker is RerankerKind.OFF else settings.ai.rerank_model,
            "member_texts": text_model(settings),
            "text_guard": settings.ai_openai.guard_model,
        },
        "photos": {
            "processed": len(entries),
            "kept": outcomes.get(KEPT, 0),
            "dropped": dict(sorted((k, v) for k, v in outcomes.items() if k != KEPT)),
            "errors": dict(sorted(errors.items())),
            "detector_available": sum(1 for entry in entries if entry["detector"]),
            "used_by_the_file": len(images_used),
        },
        "insights": len(document["insights"]),
        "posts": {
            "total": len(document["posts"]),
            "with_insight": sum(1 for b, _ in briefs if b.role != SPONSOR),
            "sponsor_notes": sum(
                1
                for e in document["map_entries"]
                if e.get("sponsor") and e["sponsor"].get("reflection")
            ),
            "with_reflection": sum(1 for p in document["posts"] if p["reflection"]),
            "failed_calls": sum(1 for entry in used if entry.get("retry")),
        },
        "comments": {
            "total": len(document["comments"]),
            "with_text": sum(1 for c in document["comments"] if c["text"]),
        },
        "texts_dropped": dict(sorted(dropped.items())),
        "evidence": evidence_counts(document),
        "usage": {"photos": photo_usage, "texts": text_usage},
        "cost_usd": {
            "photos": round(cost_of(photo_usage), 4),
            "texts": round(cost_of(text_usage), 4),
            "total": round(cost_of(photo_usage) + cost_of(text_usage), 4),
        },
        "checks": problems or "passed",
    }


# ─── The real services ───


async def download(http: httpx.AsyncClient, url: str) -> bytes:
    """Fetch one placepix photo; a refusal or an error is a DownloadError naming it."""
    try:
        response = await http.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True)
    except httpx.HTTPError as error:
        raise DownloadError(type(error).__name__) from None
    if response.status_code != httpx.codes.OK:
        message = f"http_{response.status_code}"
        raise DownloadError(message)
    if len(response.content) > MAX_PHOTO_BYTES:
        message = "too_large"
        raise DownloadError(message)
    return response.content


async def check_text(
    text: str,
    limit: int,
    *,
    sessions: Callable[[], contextlib.AbstractAsyncContextManager[AsyncSession]],
    guard: Callable[[str], Awaitable[GuardVerdict]],
    sleep: Callable[[float], Awaitable[None]],
) -> str | None:
    """What a member's text passes: the schemas' cleaning, the scripture guard, the moderation."""
    if cleaned(text, limit) is None:
        return "invalid"
    async with sessions() as db:
        if await leaks(db, [text], []):
            return "scripture"
    verdict = await guard(text)
    for attempt in range(1, ATTEMPTS):
        if verdict.reason != GUARD_UNAVAILABLE:
            break
        await sleep(BACKOFF_SECONDS * attempt)
        verdict = await guard(text)
    return verdict_reason(verdict)


async def validate_file(engine: AsyncEngine, raw: bytes) -> list[str]:
    """
    Run the importer's checks over the file, reading the store only; return what fails.

    Its shape and version, the scripture guard over every text, and every evidence id of a
    kept insight present in the store (the same function the importer runs before it writes).
    """
    try:
        data = parse(raw)
    except MockImportError as error:
        return [str(error)]
    async with rolled_back(engine) as sessions, sessions() as db:
        try:
            await check_scripture_guard(db, data)
            check_member_texts(data)
        except MockImportError as error:
            return [str(error)]
        missing = await import_mock._missing_evidence(db, data)  # noqa: SLF001 - the importer's own check
    return [f"evidence missing from the store for placepix {pid}" for pid in sorted(missing)]


@contextlib.asynccontextmanager
async def real_services(settings: Settings, parallel: int) -> AsyncIterator[Services]:
    """The services of a real run: placepix, the providers, the detector, the database."""
    gate = asyncio.Semaphore(parallel)
    engine = get_engine()
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http:
        detector = CappedDetector(
            settings.detector_url, http, timeout_seconds=settings.detector_timeout_seconds
        )

        def tools_for(provider: AiProvider) -> ScanTools:
            chosen = settings.model_copy(update={"ai_provider": provider})

            def client(log: CallLog) -> ModelClient:
                return Throttled(client_for(chosen, http, log=log), gate)

            return ScanTools(
                settings=chosen,
                engine=engine,
                detector=detector,
                client_factory=client,
                engine_factory=lambda c, sessions: build_engine(chosen, http, sessions, client=c),
            )

        tools = {provider: tools_for(provider) for provider in AiProvider}
        writer = Throttled(client_for(settings, http), gate)
        text_guard = OpenAiTextGuard(settings)

        async def scan(photo: bytes, scan_id: str, provider: AiProvider) -> ScanResult:
            return await run_scan(tools[provider], photo, scan_id)

        async def voices(brief: Brief) -> tuple[Voices, CallRecord]:
            return await ask(writer, brief, text_model(settings))

        @contextlib.asynccontextmanager
        async def read_session() -> AsyncIterator[AsyncSession]:
            async with rolled_back(engine) as sessions, sessions() as db:
                yield db

        async def guard(text: str) -> GuardVerdict:
            async with gate:
                return await text_guard.check(text)

        async def check(text: str, limit: int) -> str | None:
            return await check_text(
                text, limit, sessions=read_session, guard=guard, sleep=asyncio.sleep
            )

        async def fetch(url: str) -> bytes:
            return await download(http, url)

        async def validate(raw: bytes) -> list[str]:
            return await validate_file(engine, raw)

        try:
            yield Services(download=fetch, scan=scan, voices=voices, check=check, validate=validate)
        finally:
            await dispose_engine()


# ─── The command ───


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m mockdata.process",
        description="Run the real pipeline over the placepix photos, or write the posts' texts.",
    )
    stages = p.add_subparsers(dest="stage", required=True)
    photos = stages.add_parser("photos", help="photos -> photo-library.json")
    photos.add_argument("--folder", type=Path, default=DATA_DIR)
    photos.add_argument(
        "--stop-at", type=int, default=STOP_AT, help="photos with an insight; 0 for all"
    )
    photos.add_argument("--parallel", type=int, default=PARALLEL)
    photos.add_argument("--limit", type=int, help="at most this many photos in this run")
    photos.add_argument("--reprocess", action="store_true", help="run the photos it holds again")
    photos.add_argument(
        "--add-hadith",
        action="store_true",
        help="run the kept photos without a hadith again; take a new insight that has one",
    )
    photos.add_argument(
        "--fallback",
        choices=[*(provider.value for provider in AiProvider), "none"],
        default=AiProvider.OPENAI.value,
        help="the provider the rest goes to when the active one keeps failing",
    )
    texts = stages.add_parser("texts", help="the posts' texts -> texts-library.json and the file")
    texts.add_argument("--file", type=Path, default=DATA_DIR / OUT_NAME)
    texts.add_argument("--parallel", type=int, default=PARALLEL)
    texts.add_argument("--limit", type=int, help="at most this many posts in this run")
    return p


def options_of(args: argparse.Namespace) -> PhotoOptions | TextOptions:
    if args.stage == "texts":
        return TextOptions(file=args.file, parallel=args.parallel, limit=args.limit)
    return PhotoOptions(
        folder=args.folder,
        stop_at=args.stop_at or None,
        parallel=args.parallel,
        limit=args.limit,
        reprocess=args.reprocess,
        add_hadith=args.add_hadith,
        fallback=None if args.fallback == "none" else AiProvider(args.fallback),
    )


async def run(
    options: PhotoOptions | TextOptions,
    settings: Settings,
    services: Callable[
        [Settings, int], contextlib.AbstractAsyncContextManager[Services]
    ] = real_services,
) -> int:
    async with services(settings, options.parallel) as built:
        if isinstance(options, TextOptions):
            return await texts_stage(options, settings, built)
        if options.add_hadith:
            return await hadith_stage(options, settings, built)
        return await photo_stage(options, settings, built)


def main(argv: Sequence[str] | None = None) -> int:
    options = options_of(parser().parse_args(argv))
    if isinstance(options, TextOptions) and not options.file.exists():
        _say(f"{options.file} does not exist: run make mock-data first")
        return 2
    return asyncio.run(run(options, load_settings()))


if __name__ == "__main__":
    raise SystemExit(main())
