from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import BaseModel
from src.ai.client import ModelImage
from src.ai.errors import AiErrorCode
from src.ai.records import CallLog, CallRecord
from src.cli import import_mock
from src.cli.import_mock import MockImportError
from src.config import AiProvider, AiStage, Settings
from src.services.moderation_guard import GuardVerdict, OpenAiTextGuard, Outcome

from mockdata import catalogue, library, process
from mockdata import patch as patch_module
from mockdata.catalogue import Photo
from mockdata.process import (
    AdaptiveGate,
    PatchOptions,
    PhotoOptions,
    Services,
    Switch,
    TextOptions,
    Throttled,
    check_text,
    download,
    merge_usage,
    post_briefs,
    reusable,
    scan_photo,
    usage_of,
    write_post,
)
from mockdata.scan import ScanResult, body_of
from mockdata.voices import Brief, Slot, Voices

from .fakes import FakeClient, failure, insight, record, settings

SCENE = {"labels": ["cat"], "ar": "قطة"}
PHOTOS = [Photo(n, f"cat-{n}.jpg", "cat", 800, 600) for n in (1, 2, 3, 4)]


def busy_record(code: AiErrorCode, *, retried: bool) -> CallRecord:
    made = record(ok=retried)
    if retried:
        return made.model_copy(update={"retried_errors": (code,)})
    return made.model_copy(update={"error_code": code})


def kept_result() -> ScanResult:
    return ScanResult("insights", body=body_of(insight()), calls=[record()], detector=True)


class Fakes:
    """Services that answer from tables: what each photo gives, what each post's model says."""

    def __init__(self) -> None:
        self.outcomes: dict[str, list[ScanResult]] = {
            "mock-1": [kept_result()],
            "mock-2": [ScanResult("people")],
            "mock-3": [ScanResult("no_relevant_evidence")],
            "mock-4": [ScanResult("vision_failed", detail="invalid_output")],
        }
        self.missing: set[str] = set()
        self.scanned: list[tuple[str, AiProvider]] = []
        self.briefs: list[Brief] = []
        self.problems: list[str] = []
        self.sleeps: list[float] = []
        self.validated: list[bytes] = []

    async def download(self, url: str) -> bytes:
        if url in self.missing:
            message = "http_404"
            raise process.DownloadError(message)
        return b"photo"

    async def scan(self, photo: bytes, scan_id: str, provider: AiProvider) -> ScanResult:
        self.scanned.append((scan_id, provider))
        queue = self.outcomes[scan_id]
        return queue.pop(0) if len(queue) > 1 else queue[0]

    async def voices(self, brief: Brief) -> tuple[Voices, CallRecord]:
        self.briefs.append(brief)
        answer = Voices.model_validate(
            {
                "reflection": f"تأمل {brief.post}",
                "comments": [{"ref": s.ref, "text": f"تعليق {s.ref}"} for s in brief.slots],
            }
        )
        return answer, record(model="writer")

    async def check(self, text: str, limit: int) -> str | None:
        return "moderation_review" if text == "تعليق c3" else None

    async def validate(self, raw: bytes) -> list[str]:
        self.validated.append(raw)
        return self.problems

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def services(self, **changes: Any) -> Services:
        built = Services(
            download=self.download,
            scan=self.scan,
            voices=self.voices,
            check=self.check,
            validate=self.validate,
            sleep=self.sleep,
        )
        return replace(built, **changes)


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    catalogue.save(tmp_path / process.CATALOGUE_NAME, PHOTOS)
    return tmp_path


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# ─── Bounding the calls ───


async def test_throttled_passes_every_call_through_one_gate() -> None:
    inner = FakeClient([{}])
    client = Throttled(inner, asyncio.Semaphore(1))
    assert client.provider is AiProvider.OVH
    assert client.settings is inner.settings

    class Empty(BaseModel):
        pass

    await client.chat_json(Empty, stage=AiStage.CHAT, system="s", user="u", model="m")
    await client.embed(["نص"], model="e", dimensions=3)
    await client.moderate_image(ModelImage(b"x", "image/jpeg"), model="g")
    await client.moderate_text("نص", model="g")
    assert [sorted(call) for call in inner.calls][1:] == [
        ["dimensions", "embed", "model"],
        ["model", "moderate_image"],
        ["model", "moderate_text"],
    ]
    assert inner.calls[0]["model"] == "m"


async def test_throttled_waits_for_the_gate() -> None:
    gate = asyncio.Semaphore(1)
    client = Throttled(FakeClient(), gate)
    await gate.acquire()
    waiting = asyncio.create_task(client.moderate_text("نص"))
    await asyncio.sleep(0)
    assert not waiting.done()
    gate.release()
    await waiting


async def test_the_gate_holds_its_limit_and_halves_it_when_the_provider_is_busy() -> None:
    gate = AdaptiveGate(2)
    entered: list[int] = []

    async def work(n: int) -> None:
        async with gate.slot():
            entered.append(n)
            assert gate.active <= gate.limit
            await asyncio.sleep(0)

    await asyncio.gather(*(work(n) for n in range(5)))
    assert sorted(entered) == [0, 1, 2, 3, 4]
    assert gate.active == 0
    gate.observe([record()])
    assert gate.limit == 2
    gate.observe([busy_record(AiErrorCode.RATE_LIMITED, retried=True)])
    assert gate.limit == 1
    assert gate.events[0]["codes"] == ["rate_limited"]
    gate.observe([busy_record(AiErrorCode.SERVER_ERROR, retried=False)])
    assert gate.limit == 1
    assert len(gate.events) == 1


def test_usage_sums_tokens_and_cost_by_model_without_any_text() -> None:
    calls = [record(), record(ok=False, cost=None), record(model="other")]
    usage = usage_of(calls)
    assert usage["ovh/fake-model"] == {
        "calls": 2,
        "failed": 1,
        "input_tokens": 200,
        "output_tokens": 40,
        "cost_usd": 0.001,
    }
    total = merge_usage([usage, usage_of([record()])])
    assert total["ovh/fake-model"]["calls"] == 3
    assert list(total) == ["ovh/fake-model", "ovh/other"]
    assert process.cost_of(total) == 0.003


# ─── The provider switch ───


def test_the_switch_goes_to_the_fallback_after_failures_in_a_row() -> None:
    switch = Switch(AiProvider.OVH, AiProvider.OPENAI)
    for _ in range(process.FALLBACK_AFTER - 1):
        switch.observe(AiProvider.OVH, "vision_failed", 5)
    switch.observe(AiProvider.OVH, "insights", 5)
    assert switch.streak == 0
    for _ in range(process.FALLBACK_AFTER):
        switch.observe(AiProvider.OVH, "model_unavailable", 9)
    assert switch.current is AiProvider.OPENAI
    assert switch.switched_after == 9
    switch.observe(AiProvider.OPENAI, "vision_failed", 10)
    switch.observe(AiProvider.OVH, "vision_failed", 10)
    assert switch.current is AiProvider.OPENAI


def test_without_a_fallback_the_switch_stays() -> None:
    switch = Switch(AiProvider.OVH, None)
    for _ in range(process.FALLBACK_AFTER + 1):
        switch.observe(AiProvider.OVH, "vision_failed", 1)
    assert switch.current is AiProvider.OVH


# ─── One photo ───


async def test_a_photo_is_retried_while_it_may_pass_later() -> None:
    fakes = Fakes()
    fakes.outcomes["mock-1"] = [ScanResult("model_unavailable", calls=[record()]), kept_result()]
    result, provider, attempts, calls = await scan_photo(
        PHOTOS[0], fakes.services(), Switch(AiProvider.OVH, None), lambda: 0
    )
    assert (result.outcome, provider, attempts, len(calls)) == ("insights", AiProvider.OVH, 2, 2)
    assert fakes.sleeps == [process.BACKOFF_SECONDS]


async def test_a_photo_that_cannot_be_fetched_is_tried_three_times() -> None:
    fakes = Fakes()
    fakes.missing.add(PHOTOS[0].url)
    result, _, attempts, calls = await scan_photo(
        PHOTOS[0], fakes.services(), Switch(AiProvider.OVH, None), lambda: 0
    )
    assert (result.outcome, result.detail, attempts, calls) == (
        "download_failed",
        "http_404",
        process.ATTEMPTS,
        [],
    )
    assert fakes.sleeps == [10.0, 20.0]
    assert process.is_retry(result)


def test_a_photo_entry_holds_what_the_owners_asked_for() -> None:
    entry = process.photo_entry(
        PHOTOS[0], kept_result(), AiProvider.OVH, 1, [record()], settings(), "2026-10-05T18:00:00Z"
    )
    assert set(entry) == {
        "url", "filename", "category", "width", "height", "scene", "outcome",
        "pipeline_outcome", "detail", "provider", "model", "detector", "attempts", "usage",
        "cost_usd", "processed_at", "insight", "insight_at",
    }  # fmt: skip
    assert entry["model"] == "Qwen3.8-27B"
    assert entry["insight"]["title"] == "سكينة القطة"
    assert entry["cost_usd"] == 0.001
    assert entry["insight_at"] == entry["processed_at"]
    failed = process.photo_entry(
        PHOTOS[0], ScanResult("vision_failed"), AiProvider.OPENAI, 1, [], settings(), "t"
    )
    assert (failed["outcome"], failed["pipeline_outcome"]) == ("error", "vision_failed")
    assert failed["model"] == "gpt-5.4-mini-2026-03-17"
    assert failed["insight"] is None


# ─── The photo stage ───


async def test_the_photo_stage_fills_the_library_and_records_the_run(folder: Path) -> None:
    fakes = Fakes()
    options = PhotoOptions(folder=folder, stop_at=None, parallel=2)
    assert await process.photo_stage(options, settings(ai_provider="ovh"), fakes.services()) == 0
    data = read(folder / library.PHOTOS_NAME)
    outcomes = {pid: entry["outcome"] for pid, entry in data["photos"].items()}
    assert outcomes == {"1": "insights", "2": "people", "3": "no_relevant_evidence", "4": "error"}
    run = data["runs"][0]
    assert (run["stage"], run["parallel"], run["fallback"], run["adopted_from_state"]) == (
        "photos",
        2,
        None,
        0,
    )
    # A second run holds every photo already: nothing is scanned again.
    fakes.scanned.clear()
    await process.photo_stage(options, settings(ai_provider="ovh"), fakes.services())
    assert fakes.scanned == []
    assert len(read(folder / library.PHOTOS_NAME)["runs"]) == 2
    await process.photo_stage(
        replace(options, reprocess=True, limit=1), settings(ai_provider="ovh"), fakes.services()
    )
    assert fakes.scanned == [("mock-1", AiProvider.OVH)]


async def test_the_photo_stage_stops_at_enough_insights(folder: Path) -> None:
    fakes = Fakes()
    fakes.outcomes = {f"mock-{p.id}": [kept_result()] for p in PHOTOS}
    options = PhotoOptions(folder=folder, stop_at=2, parallel=1)
    await process.photo_stage(options, settings(), fakes.services())
    assert sorted(read(folder / library.PHOTOS_NAME)["photos"]) == ["1", "2"]


async def test_a_library_that_holds_enough_runs_nothing(folder: Path) -> None:
    fakes = Fakes()
    await process.photo_stage(PhotoOptions(folder=folder, limit=1), settings(), fakes.services())
    fakes.scanned.clear()
    await process.photo_stage(PhotoOptions(folder=folder, stop_at=1), settings(), fakes.services())
    assert fakes.scanned == []


async def test_the_photos_still_running_are_stopped_not_dropped(folder: Path) -> None:
    fakes = Fakes()
    release = asyncio.Event()

    async def scan(photo: bytes, scan_id: str, provider: AiProvider) -> ScanResult:
        if scan_id != "mock-1":
            await release.wait()
        return kept_result()

    options = PhotoOptions(folder=folder, stop_at=1, parallel=4)
    await process.photo_stage(options, settings(), fakes.services(scan=scan))
    assert sorted(read(folder / library.PHOTOS_NAME)["photos"]) == ["1"]


async def test_a_photo_that_may_pass_later_stays_out_of_the_library(folder: Path) -> None:
    fakes = Fakes()
    fakes.outcomes["mock-2"] = [ScanResult("source_unavailable")]
    options = PhotoOptions(folder=folder, stop_at=None, limit=2)
    await process.photo_stage(options, settings(), fakes.services())
    data = read(folder / library.PHOTOS_NAME)
    assert sorted(data["photos"]) == ["1"]
    assert data["runs"][0]["outcomes"] == {"insights": 1, "source_unavailable": 1}


async def test_a_busy_provider_lowers_the_parallel_photos(folder: Path) -> None:
    fakes = Fakes()
    busy = busy_record(AiErrorCode.RATE_LIMITED, retried=True)
    fakes.outcomes["mock-1"] = [ScanResult("people", calls=[busy])]
    options = PhotoOptions(folder=folder, stop_at=None, parallel=4)
    await process.photo_stage(options, settings(), fakes.services())
    throttled = read(folder / library.PHOTOS_NAME)["runs"][0]["throttled"]
    assert [event["limit"] for event in throttled] == [2]


async def test_the_fallback_takes_the_rest_and_is_recorded(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fakes = Fakes()
    fakes.outcomes = {f"mock-{p.id}": [ScanResult("vision_failed")] for p in PHOTOS}
    monkeypatch.setattr(process, "FALLBACK_AFTER", 2)
    options = PhotoOptions(folder=folder, stop_at=None, parallel=1)
    await process.photo_stage(options, settings(ai_provider="ovh"), fakes.services())
    assert [provider for _, provider in fakes.scanned] == [
        AiProvider.OVH,
        AiProvider.OVH,
        AiProvider.OPENAI,
        AiProvider.OPENAI,
    ]
    run = read(folder / library.PHOTOS_NAME)["runs"][0]
    assert run["fallback"] == {"to": "openai", "after_photos": 1}


async def test_no_fallback_when_it_is_the_active_provider(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fakes = Fakes()
    fakes.outcomes = {f"mock-{p.id}": [ScanResult("vision_failed")] for p in PHOTOS}
    monkeypatch.setattr(process, "FALLBACK_AFTER", 1)
    options = PhotoOptions(folder=folder, stop_at=None, parallel=1)
    await process.photo_stage(options, settings(ai_provider="openai"), fakes.services())
    assert {provider for _, provider in fakes.scanned} == {AiProvider.OPENAI}


async def test_an_earlier_runs_state_is_adopted_once(folder: Path) -> None:
    state = {
        "images": {
            "1": {
                "outcome": "insights",
                "detail": None,
                "detector": True,
                "provider": "ovh",
                "attempts": 1,
                "retry": False,
                "insight": body_of(insight()),
                "usage": {"ovh/m": {"calls": 2, "cost_usd": 0.5}},
            },
            "2": {"outcome": "model_unavailable", "retry": True},
            "99": {"outcome": "people", "retry": False},
        }
    }
    (folder / process.STATE_NAME).write_text(json.dumps(state), encoding="utf-8")
    fakes = Fakes()
    options = PhotoOptions(folder=folder, stop_at=None, parallel=1)
    await process.photo_stage(options, settings(), fakes.services())
    data = read(folder / library.PHOTOS_NAME)
    assert data["photos"]["1"]["cost_usd"] == 0.5
    assert data["photos"]["1"]["processed_at"].endswith("Z")
    assert data["runs"][0]["adopted_from_state"] == 1
    assert "mock-1" not in [scan_id for scan_id, _ in fakes.scanned]
    assert "mock-2" in [scan_id for scan_id, _ in fakes.scanned]
    await process.photo_stage(options, settings(), fakes.services())
    assert read(folder / library.PHOTOS_NAME)["runs"][1]["adopted_from_state"] == 0


# ─── The hadith pass ───


def kept_entry(*, hadith: bool, cost: float = 0.5) -> dict[str, Any]:
    return {
        "outcome": "insights",
        "processed_at": "2026-10-05T18:00:00Z",
        "insight": body_of(insight(hadith=hadith)),
        "usage": {"ovh/fake-model": {"calls": 2, "failed": 0, "input_tokens": 1,
                                     "output_tokens": 1, "cost_usd": cost}},
        "cost_usd": cost,
    }  # fmt: skip


def new_result(*, hadith: bool, outcome: str = "insights") -> ScanResult:
    body = body_of(insight(hadith=hadith)) | {"title": "عنوان جديد"}
    return ScanResult(outcome, body=body if outcome == "insights" else None, calls=[record()])


def test_a_new_insight_is_taken_whole_only_when_it_carries_a_hadith() -> None:
    old = kept_entry(hadith=False)
    taken, what = process.with_new_insight(old, new_result(hadith=True), [record()], "T")
    assert what == "hadith_added"
    assert (taken["insight"]["title"], taken["insight_at"]) == ("عنوان جديد", "T")
    assert taken["insight"]["hadith"]["number"] == "1"
    assert taken["cost_usd"] == 0.501
    assert taken["usage"]["ovh/fake-model"]["calls"] == 3
    assert (taken["outcome"], taken["processed_at"]) == ("insights", "2026-10-05T18:00:00Z")
    kept, what = process.with_new_insight(old, new_result(hadith=False), [record()], "T")
    assert what == "kept_old:no_hadith"
    assert kept["insight"] == old["insight"]
    assert "insight_at" not in kept
    lost, what = process.with_new_insight(old, new_result(hadith=True, outcome="people"), [], "T")
    assert what == "kept_old:people"
    assert lost["insight"] == old["insight"]
    assert lost["cost_usd"] == 0.5


async def test_the_hadith_pass_runs_only_the_kept_photos_without_a_hadith(folder: Path) -> None:
    photos = library.photos(folder / library.PHOTOS_NAME)
    photos.entries.update(
        {
            "1": kept_entry(hadith=False),
            "2": kept_entry(hadith=True),
            "3": kept_entry(hadith=False),
            "4": {"outcome": "people", "insight": None},
        }
    )
    await photos.save()
    fakes = Fakes()
    fakes.outcomes["mock-1"] = [new_result(hadith=True)]
    fakes.outcomes["mock-3"] = [ScanResult("source_unavailable", calls=[record()])]
    options = PhotoOptions(folder=folder, parallel=2, add_hadith=True)
    assert await process.hadith_stage(options, settings(ai_provider="ovh"), fakes.services()) == 0
    assert sorted(scan_id for scan_id, _ in fakes.scanned) == [
        "mock-1",
        "mock-3",
        "mock-3",
        "mock-3",
    ]
    data = read(folder / library.PHOTOS_NAME)
    assert data["photos"]["1"]["insight"]["title"] == "عنوان جديد"
    assert data["photos"]["2"] == kept_entry(hadith=True)
    assert data["photos"]["3"]["insight"]["hadith"] is None
    assert data["photos"]["3"]["cost_usd"] == 0.503
    run = data["runs"][-1]
    assert (run["stage"], run["photos"], run["outcomes"]) == (
        "hadith",
        2,
        {"hadith_added": 1, "retry": 1},
    )
    fakes.scanned.clear()
    await process.hadith_stage(replace(options, limit=0), settings(), fakes.services())
    assert fakes.scanned == []


# ─── The texts stage ───


def mock_file() -> dict[str, Any]:
    """Three photos, two members, posts and comments: the generator's shape, values invented."""
    return {
        "version": 1,
        "seed": 1,
        "generated_at": "2026-10-05T10:00:00Z",
        "images": [
            {"placepix_id": 1, "scene": SCENE, "insight": body_of(insight())},
            {"placepix_id": 2, "scene": SCENE, "insight": body_of(insight(step=False))},
            {"placepix_id": 3, "scene": SCENE, "insight": None},
        ],
        "members": [{"ref": "m1", "country": "TN"}, {"ref": "m2", "country": "EG"}],
        "insights": [
            {"ref": "i1", "member": "m1", "image": 1},
            {"ref": "i2", "member": "m2", "image": 2},
            {"ref": "i3", "member": "m2", "image": 3},
        ],
        "posts": [
            {"ref": "p1", "insight": "i1", "reflection": None},
            {"ref": "p2", "insight": "i2", "reflection": None, "reflect": False},
            {"ref": "p3", "insight": "i9", "reflection": None},
            {"ref": "p4", "insight": "i3", "reflection": None},
        ],
        "map_entries": [
            {"insight": "i1", "sponsor": {"member": "m2", "reflection": None}},
            {"insight": "i2", "sponsor": None},
            {"insight": "i3", "sponsor": {"member": "m1", "reflection": None}},
            {"insight": "i9", "sponsor": {"member": "m1", "reflection": None}},
        ],
        "comments": [
            {"ref": "c1", "post": "p1", "member": "m2", "parent": None, "text": None},
            {"ref": "c2", "post": "p1", "member": "m1", "parent": "c1", "text": None},
            {"ref": "c3", "post": "p2", "member": "m1", "parent": None, "text": None},
            {"ref": "c4", "post": "p4", "member": "m1", "parent": None, "text": None},
        ],
    }


def write_file(folder: Path) -> Path:
    path = folder / "tabsira-mock-v1.json"
    path.write_text(json.dumps(mock_file()), encoding="utf-8")
    return path


def test_briefs_are_the_posts_of_photos_with_an_insight() -> None:
    found = post_briefs(mock_file())
    assert [(brief.post, pid) for brief, pid in found] == [
        ("p1", 1),
        ("p2", 2),
        ("sponsor:i1", 1),
    ]
    sponsor = found[2][0]
    assert (sponsor.role, sponsor.country, sponsor.slots) == ("sponsor", "EG", ())
    assert found[0][0].role == "author"
    assert found[0][0].country == "TN"
    assert found[0][0].slots == (Slot("c1", None, "EG"), Slot("c2", "c1", "TN"))
    assert found[1][0].step is None


def test_a_library_entry_is_reused_only_for_the_same_slots() -> None:
    brief = Brief("p1", "t", "g", None, "TN", (Slot("c1", None, "EG"),))
    assert reusable({"slots": [["c1", None]]}, brief)
    assert not reusable({"slots": [["c2", None]]}, brief)
    assert not reusable({"slots": [["c1", None]], "retry": True}, brief)
    assert not reusable(None, brief)


def test_a_library_entry_written_before_its_photos_insight_is_written_again() -> None:
    brief = Brief("p1", "t", "g", None, "TN", (Slot("c1", None, "EG"),))
    entry = {"slots": [["c1", None]], "written_at": "2026-10-05T18:30:00Z"}
    assert reusable(entry, brief, "2026-10-05T18:20:00Z")
    assert reusable(entry, brief, "2026-10-05T18:30:00Z")
    assert not reusable(entry, brief, "2026-10-05T20:00:00Z")
    assert not reusable({"slots": [["c1", None]]}, brief, "2026-10-05T18:20:00Z")


async def test_the_texts_stage_writes_again_the_posts_of_a_new_insight(folder: Path) -> None:
    fakes = Fakes()
    path = write_file(folder)
    await process.texts_stage(TextOptions(path), settings(), fakes.services())
    photos = library.photos(folder / library.PHOTOS_NAME)
    photos.entries["1"] = _photo("insights", "insights") | {"insight_at": "2999-01-01T00:00:00Z"}
    await photos.save()
    fakes.briefs.clear()
    await process.texts_stage(TextOptions(path), settings(), fakes.services())
    # The post and the sponsor's note of the photo's insight, nothing else.
    assert sorted(brief.post for brief in fakes.briefs) == ["p1", "sponsor:i1"]


async def test_a_post_whose_call_fails_is_retried_then_left_for_the_next_run() -> None:
    fakes = Fakes()
    calls = 0

    async def failing(brief: Brief) -> tuple[Voices, CallRecord]:
        nonlocal calls
        calls += 1
        raise failure("timeout", with_record=calls == 1)

    entry, records = await write_post(
        Brief("p1", "t", "g", None, "TN", ()), fakes.services(voices=failing)
    )
    assert (entry["retry"], entry["error"]) == (True, "timeout")
    assert entry["usage"]["ovh/fake-model"]["failed"] == 1
    assert len(records) == 1
    assert calls == process.ATTEMPTS


async def test_a_post_that_passes_on_a_later_call() -> None:
    fakes = Fakes()
    answers: list[Exception] = [failure("rate_limited")]

    async def flaky(brief: Brief) -> tuple[Voices, CallRecord]:
        if answers:
            raise answers.pop()
        return await fakes.voices(brief)

    brief = Brief("p2", "t", "g", None, "EG", (Slot("c3", None, "TN"),))
    entry, _ = await write_post(brief, fakes.services(voices=flaky))
    assert entry["reflection"] == "تأمل p2"
    assert entry["comments"] == {"c3": None}
    assert entry["dropped"] == {"comment_moderation_review": 1}
    assert sorted(entry["usage"]) == ["ovh/fake-model", "ovh/writer"]


def _photo(outcome: str, pipeline: str) -> dict[str, Any]:
    return {
        "outcome": outcome,
        "pipeline_outcome": pipeline,
        "provider": "ovh",
        "detector": True,
        "usage": {"ovh/m": {"calls": 1, "cost_usd": 0.1}},
    }


async def test_the_texts_stage_writes_the_file_the_library_and_the_report(folder: Path) -> None:
    path = write_file(folder)
    photos = library.photos(folder / library.PHOTOS_NAME)
    await photos.put("1", _photo("insights", "insights"))
    await photos.put("4", _photo("error", "vision_failed"))
    fakes = Fakes()
    assert await process.texts_stage(TextOptions(path), settings(), fakes.services()) == 0
    out = read(path)
    # The library keeps p2's text; the post leaves it out because its author wrote none.
    assert [post["reflection"] for post in out["posts"]] == ["تأمل p1", None, None, None]
    assert out["map_entries"][0]["sponsor"]["reflection"] == "تأمل sponsor:i1"
    assert out["map_entries"][1]["sponsor"] is None
    assert out["map_entries"][2]["sponsor"]["reflection"] is None
    assert [c["text"] for c in out["comments"]] == ["تعليق c1", "تعليق c2", None, None]
    assert fakes.validated == [path.read_bytes()]
    texts = read(folder / library.TEXTS_NAME)
    assert sorted(texts["posts"]) == ["p1:1", "p2:2", "sponsor:i1:1"]
    assert texts["posts"]["p2:2"]["reflection"] == "تأمل p2"
    assert texts["posts"]["p1:1"]["slots"] == [["c1", None], ["c2", "c1"]]
    report = read(folder / process.REPORT_NAME)
    assert report["photos"]["kept"] == 1
    assert report["photos"]["errors"] == {"vision_failed": 1}
    assert report["posts"]["with_reflection"] == 1
    assert report["posts"]["with_insight"] == 2
    assert report["posts"]["sponsor_notes"] == 1
    assert report["comments"]["with_text"] == 2
    assert report["texts_dropped"] == {"comment_moderation_review": 1}
    assert report["evidence"]["distinct_verses"] == 1
    assert report["cost_usd"]["texts"] == 0.003
    assert report["models"]["rerank"] == "off"
    assert report["checks"] == "passed"

    # A second run reuses every text: no call, the same file.
    fakes.briefs.clear()
    before = path.read_bytes()
    assert await process.texts_stage(TextOptions(path), settings(), fakes.services()) == 0
    assert fakes.briefs == []
    assert path.read_bytes() == before


async def test_a_file_that_fails_the_checks_is_not_written(folder: Path) -> None:
    path = write_file(folder)
    before = path.read_bytes()
    fakes = Fakes()
    fakes.problems = ["the scripture guard refuses the text at post.p1"]
    code = await process.texts_stage(TextOptions(path, limit=1), settings(), fakes.services())
    assert code == 1
    assert path.read_bytes() == before
    assert read(folder / process.REPORT_NAME)["checks"] == fakes.problems
    assert [brief.post for brief in fakes.briefs] == ["p1"]


async def test_a_texts_run_that_stops_records_itself(folder: Path) -> None:
    path = write_file(folder)
    fakes = Fakes()

    async def broken(brief: Brief) -> tuple[Voices, CallRecord]:
        raise RuntimeError

    with pytest.raises(RuntimeError):
        await process.texts_stage(TextOptions(path), settings(), fakes.services(voices=broken))
    assert read(folder / library.TEXTS_NAME)["runs"][0]["stage"] == "texts"


async def test_a_busy_writer_lowers_the_parallel_posts(folder: Path) -> None:
    path = write_file(folder)
    fakes = Fakes()

    async def busy(brief: Brief) -> tuple[Voices, CallRecord]:
        voices, _ = await fakes.voices(brief)
        return voices, busy_record(AiErrorCode.SERVER_ERROR, retried=True)

    options = TextOptions(path, parallel=4)
    await process.texts_stage(options, settings(), fakes.services(voices=busy))
    throttled = read(folder / library.TEXTS_NAME)["runs"][0]["throttled"]
    assert [event["limit"] for event in throttled] == [2, 1]


# ─── The real services ───


async def test_download_returns_the_photo_or_says_why_not() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ok":
            return httpx.Response(200, content=b"jpeg")
        if request.url.path == "/big":
            return httpx.Response(200, content=b"x" * (process.MAX_PHOTO_BYTES + 1))
        if request.url.path == "/down":
            message = "down"
            raise httpx.ConnectError(message)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http:
        assert await download(http, "https://placepix.net/ok") == b"jpeg"
        for path, reason in (
            ("/big", "too_large"),
            ("/gone", "http_404"),
            ("/down", "ConnectError"),
        ):
            with pytest.raises(process.DownloadError, match=reason):
                await download(http, f"https://placepix.net{path}")


@contextlib.asynccontextmanager
async def no_session() -> AsyncIterator[Any]:
    yield object()


async def test_check_text_runs_the_cleaning_the_guard_and_the_moderation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leaked: list[str] = []

    async def leaks(db: object, texts: list[str], corpus: list[str]) -> bool:
        leaked.extend(texts)
        return texts == ["نص منقول"]

    monkeypatch.setattr(process, "leaks", leaks)
    verdicts = [GuardVerdict(Outcome.REVIEW, process.GUARD_UNAVAILABLE)] * 2 + [
        GuardVerdict(Outcome.ALLOW, "clear")
    ]
    sleeps: list[float] = []

    async def guard(text: str) -> GuardVerdict:
        return verdicts.pop(0)

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    def run(text: str, limit: int = 500) -> Any:
        return check_text(text, limit, sessions=no_session, guard=guard, sleep=sleep)

    assert await run(chr(0x202E)) == "invalid"
    assert await run("نص منقول") == "scripture"
    assert await run("نص سليم") is None
    assert sleeps == [10.0, 20.0]
    verdicts[:] = [GuardVerdict(Outcome.REVIEW, process.GUARD_UNAVAILABLE)] * 3
    assert await run("نص آخر") == "moderation_review"
    verdicts[:] = [GuardVerdict(Outcome.REJECT, "harassment")]
    assert await run("نص ثالث") == "moderation_reject"
    assert leaked == ["نص منقول", "نص سليم", "نص آخر", "نص ثالث"]


async def test_validate_file_runs_the_importers_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextlib.asynccontextmanager
    async def fake_rolled_back(engine: object) -> AsyncIterator[Callable[[], Any]]:
        yield no_session

    refused: list[str] = []

    async def guard(db: object, data: object) -> None:
        if refused:
            raise MockImportError(refused[0])

    async def missing(db: object, data: object) -> set[int]:
        return {7, 3}

    monkeypatch.setattr(process, "rolled_back", fake_rolled_back)
    monkeypatch.setattr(process, "check_scripture_guard", guard)
    monkeypatch.setattr(import_mock, "_missing_evidence", missing)
    raw = json.dumps({"version": 1}).encode()
    engine: Any = object()
    assert await process.validate_file(engine, raw) == [
        "evidence missing from the store for placepix 3",
        "evidence missing from the store for placepix 7",
    ]
    refused.append("the scripture guard refuses the text at post.p1")
    assert await process.validate_file(engine, raw) == refused
    assert "not JSON" in (await process.validate_file(engine, b"{"))[0]


async def test_the_real_services_wire_the_providers_the_store_and_the_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disposed: list[bool] = []
    seen: dict[str, Any] = {}

    async def dispose() -> None:
        disposed.append(True)

    async def run_scan(tools: Any, photo: bytes, scan_id: str) -> ScanResult:
        client = tools.client_factory(CallLog())
        seen["scan"] = (tools.settings.ai_provider, scan_id, type(client).__name__)
        seen["engine"] = tools.engine_factory(client, object())
        return ScanResult("people")

    async def ask(client: Any, brief: Brief, model: str) -> tuple[Voices, Any]:
        seen["ask"] = (type(client).__name__, model)
        return Voices(reflection="ر", comments=[]), record()

    async def fake_download(http: object, url: str) -> bytes:
        return url.encode()

    async def fake_validate(engine: object, raw: bytes) -> list[str]:
        return ["checked"]

    async def fake_check(text: str, limit: int, **parts: Any) -> str | None:
        async with parts["sessions"]() as db:
            seen["session"] = db
        seen["verdict"] = await parts["guard"](text)
        return None

    async def fake_guard(self: object, text: str) -> GuardVerdict:
        return GuardVerdict(Outcome.ALLOW, "clear")

    @contextlib.asynccontextmanager
    async def fake_rolled_back(engine: object) -> AsyncIterator[Callable[[], Any]]:
        yield no_session

    monkeypatch.setattr(process, "get_engine", lambda: "engine")
    monkeypatch.setattr(process, "dispose_engine", dispose)
    monkeypatch.setattr(process, "run_scan", run_scan)
    monkeypatch.setattr(process, "ask", ask)
    monkeypatch.setattr(process, "download", fake_download)
    monkeypatch.setattr(process, "validate_file", fake_validate)
    monkeypatch.setattr(process, "check_text", fake_check)
    monkeypatch.setattr(process, "rolled_back", fake_rolled_back)
    monkeypatch.setattr(OpenAiTextGuard, "check", fake_guard)
    monkeypatch.setattr(process, "build_engine", lambda *args, **kwargs: "built")

    async with process.real_services(settings(ai_provider="ovh"), 3) as services:
        assert await services.scan(b"p", "mock-1", AiProvider.OPENAI) == ScanResult("people")
        assert seen["scan"] == (AiProvider.OPENAI, "mock-1", "Throttled")
        assert seen["engine"] == "built"
        await services.voices(Brief("p1", "t", "g", None, "TN", ()))
        assert seen["ask"] == ("Throttled", "Qwen3.8-27B")
        assert await services.download("u") == b"u"
        assert await services.validate(b"{}") == ["checked"]
        assert await services.check("نص", 500) is None
        assert seen["verdict"].outcome is Outcome.ALLOW
    assert disposed == [True]


# ─── The command ───


def test_options_from_the_command_line(tmp_path: Path) -> None:
    photos = process.options_of(
        process.parser().parse_args(
            ["photos", "--folder", str(tmp_path), "--stop-at", "0", "--parallel", "5",
             "--limit", "3", "--reprocess", "--fallback", "none", "--add-hadith"]
        )
    )  # fmt: skip
    assert photos == PhotoOptions(
        folder=tmp_path,
        stop_at=None,
        parallel=5,
        limit=3,
        reprocess=True,
        fallback=None,
        add_hadith=True,
    )
    only = process.options_of(process.parser().parse_args(["photos", "--only", "3,1"]))
    assert only == PhotoOptions(only=frozenset({1, 3}))
    patched = process.options_of(
        process.parser().parse_args(["patch", "--photos", "2", "--file", str(tmp_path / "f.json")])
    )
    assert patched == PatchOptions(file=tmp_path / "f.json", photos=frozenset({2}))
    withdrawn = process.options_of(
        process.parser().parse_args(["patch", "--photos", "2", "--withdraw", "unrelated"])
    )
    assert withdrawn.withdraw == "unrelated"
    with pytest.raises(SystemExit):
        process.parser().parse_args(["photos", "--only", "1", "--add-hadith"])
    default = process.options_of(process.parser().parse_args(["photos"]))
    assert default == PhotoOptions()
    texts = process.options_of(
        process.parser().parse_args(["texts", "--file", str(tmp_path / "f.json"), "--limit", "2"])
    )
    assert texts == TextOptions(file=tmp_path / "f.json", parallel=20, limit=2)


async def test_run_builds_the_services_for_each_stage(folder: Path) -> None:
    fakes = Fakes()
    given: list[int] = []

    @contextlib.asynccontextmanager
    async def services(loaded: Settings, parallel: int) -> AsyncIterator[Services]:
        given.append(parallel)
        yield fakes.services()

    photos = PhotoOptions(folder=folder, stop_at=None, parallel=3)
    assert await process.run(photos, settings(), services) == 0
    texts = TextOptions(write_file(folder), parallel=4)
    assert await process.run(texts, settings(), services) == 0
    hadith = PhotoOptions(folder=folder, parallel=5, add_hadith=True)
    assert await process.run(hadith, settings(), services) == 0
    patch = PatchOptions(write_file(folder), photos=frozenset({1}))
    await library.photos(folder / library.PHOTOS_NAME).put("1", library_entry(body_of(insight())))
    assert await process.run(patch, settings(), services) == 0
    assert given == [3, 4, 5, 1]


def test_main_needs_the_file_for_the_texts_and_the_patch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert process.main(["texts", "--file", str(tmp_path / "none.json")]) == 2
    assert "make mock-data" in capsys.readouterr().out
    assert process.main(["patch", "--photos", "1", "--file", str(tmp_path / "none.json")]) == 2


def test_main_runs_with_the_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    given: list[Any] = []

    async def run(options: Any, loaded: Settings) -> int:
        given.append((options, loaded))
        return 0

    monkeypatch.setattr(process, "run", run)
    monkeypatch.setattr(process, "load_settings", lambda: "settings")
    assert process.main(["photos", "--folder", str(tmp_path)]) == 0
    assert given == [(PhotoOptions(folder=tmp_path), "settings")]


async def test_the_detector_takes_a_few_calls_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    running = peak = 0

    async def slow(self: Any, request: Any) -> str:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1
        return "done"

    monkeypatch.setattr("src.pipeline.detector.DetectorClient.detect", slow)
    async with httpx.AsyncClient() as http:
        detector = process.CappedDetector("http://detector", http, timeout_seconds=1.0, limit=2)
        results = await asyncio.gather(*(detector.detect(object()) for _ in range(6)))  # type: ignore[arg-type]

    assert list(results) == ["done"] * 6  # type: ignore[comparison-overlap]
    assert peak == 2


# ─── Photos run again, one by one (--only) ───


async def test_only_runs_exactly_those_photos_again_and_keeps_their_cost(folder: Path) -> None:
    photos = library.photos(folder / library.PHOTOS_NAME)
    await photos.put("1", kept_entry(hadith=False, cost=0.5))
    await photos.put("2", kept_entry(hadith=True, cost=0.5))
    fakes = Fakes()
    fakes.outcomes["mock-1"] = [new_result(hadith=True)]
    fakes.outcomes["mock-3"] = [ScanResult("people", calls=[record()])]
    # `stop_at` would be met by the kept photo 2: it does not apply to `only`.
    options = PhotoOptions(folder=folder, stop_at=1, parallel=2, only=frozenset({1, 3}))
    assert await process.photo_stage(options, settings(), fakes.services()) == 0
    assert sorted(scan_id for scan_id, _ in fakes.scanned) == ["mock-1", "mock-3"]
    data = read(folder / library.PHOTOS_NAME)
    assert data["photos"]["1"]["insight"]["title"] == "عنوان جديد"
    assert data["photos"]["1"]["insight"]["hadith"]["number"] == "1"
    assert data["photos"]["1"]["cost_usd"] == 0.501
    assert data["photos"]["1"]["usage"]["ovh/fake-model"]["calls"] == 3
    assert data["photos"]["3"]["outcome"] == "people"
    assert data["photos"]["3"]["insight"] is None
    assert data["photos"]["2"] == kept_entry(hadith=True, cost=0.5)
    assert "4" not in data["photos"]
    assert data["runs"][-1]["only"] == [1, 3]


async def test_a_photo_that_leaves_the_insights_says_so_in_the_library(folder: Path) -> None:
    photos = library.photos(folder / library.PHOTOS_NAME)
    await photos.put("1", kept_entry(hadith=True))
    fakes = Fakes()
    fakes.outcomes["mock-1"] = [ScanResult("sensitive", calls=[record()])]
    options = PhotoOptions(folder=folder, only=frozenset({1}))
    await process.photo_stage(options, settings(), fakes.services())
    entry = read(folder / library.PHOTOS_NAME)["photos"]["1"]
    assert (entry["outcome"], entry["insight"]) == ("sensitive", None)


async def test_a_photo_that_may_pass_later_keeps_its_entry_under_only(folder: Path) -> None:
    photos = library.photos(folder / library.PHOTOS_NAME)
    await photos.put("1", kept_entry(hadith=True))
    fakes = Fakes()
    fakes.outcomes["mock-1"] = [ScanResult("source_unavailable", calls=[record()])]
    await process.photo_stage(
        PhotoOptions(folder=folder, only=frozenset({1})), settings(), fakes.services()
    )
    assert read(folder / library.PHOTOS_NAME)["photos"]["1"] == kept_entry(hadith=True)


async def test_only_refuses_an_id_the_catalogue_does_not_hold(
    folder: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fakes = Fakes()
    options = PhotoOptions(folder=folder, only=frozenset({1, 77, 12}))
    assert await process.photo_stage(options, settings(), fakes.services()) == 2
    assert "12, 77" in capsys.readouterr().out
    assert fakes.scanned == []
    assert not (folder / library.PHOTOS_NAME).exists()


# ─── The patch stage ───


def library_entry(
    body: dict[str, Any] | None, outcome: str = "insights", scene: dict[str, Any] = SCENE
) -> dict[str, Any]:
    return {
        "outcome": outcome,
        "scene": scene,
        "insight": body,
        "processed_at": "2026-10-05T18:00:00Z",
        "insight_at": "2026-10-05T18:00:00Z",
        "pipeline_outcome": outcome,
        "provider": "ovh",
        "detector": True,
        "usage": {},
    }


async def patch_library(folder: Path) -> None:
    """The photo library after `photos --only 1,2,3,9`: 1 has a new insight, 2 left, 3 gained."""
    photos = library.photos(folder / library.PHOTOS_NAME)
    new = body_of(insight(hadith=False)) | {"title": "عنوان جديد"}
    await photos.put("1", library_entry(new))
    await photos.put("2", library_entry(None, "people"))
    await photos.put("3", library_entry(body_of(insight(quran=False))))
    await photos.put("9", library_entry(body_of(insight())))


async def test_the_patch_changes_the_listed_photos_and_nothing_else(folder: Path) -> None:
    path = folder / "tabsira-mock-v1.json"
    before = mock_file()
    path.write_text(library.dumps(before) + "\n", encoding="utf-8")
    await patch_library(folder)
    fakes = Fakes()
    options = PatchOptions(path, frozenset({1, 2, 3, 9}))
    assert await process.patch_stage(options, settings(), fakes.services()) == 0
    after = read(path)
    assert {k: v for k, v in after.items() if k != "images"} == {
        k: v for k, v in before.items() if k != "images"
    }
    first, second, third = after["images"]
    assert first["insight"]["title"] == "عنوان جديد"
    assert first["insight"]["hadith"] is None
    assert second["insight"] is None
    assert third["insight"]["quran"] is None
    assert third["insight"]["hadith"]["number"] == "1"
    assert fakes.validated == [path.read_bytes()]
    report = read(folder / patch_module.PATCH_REPORT_NAME)
    assert report["checks"] == "passed"
    assert report["result"] == {"emptied": 1, "filled": 1, "not_in_file": 1, "replaced": 1}
    by_photo = {change["photo"]: change for change in report["photos"]}
    assert by_photo[1]["from"] == {"quran": "2:164", "hadith": "bukhari:1"}
    assert by_photo[1]["to"] == {"quran": "2:164", "hadith": None}
    assert (by_photo[2]["to"], by_photo[2]["outcome"]) == (None, "people")
    assert by_photo[9] == {"photo": 9, "result": "not_in_file", "outcome": "insights"}
    # Only the changed photos' insights are marked new, for the texts stage.
    stamped = read(folder / library.PHOTOS_NAME)["photos"]
    assert stamped["1"]["insight_at"] > "2026-10-05T18:00:00Z"
    assert stamped["9"]["insight_at"] == "2026-10-05T18:00:00Z"

    # Again: nothing differs, the file keeps its bytes and the texts are not made stale.
    written = path.read_bytes()
    assert await process.patch_stage(options, settings(), fakes.services()) == 0
    assert path.read_bytes() == written
    assert read(folder / patch_module.PATCH_REPORT_NAME)["result"] == {
        "not_in_file": 1,
        "unchanged": 3,
    }
    assert read(folder / library.PHOTOS_NAME)["photos"] == stamped


async def test_a_withdrawn_photo_is_emptied_and_kept_out_of_the_library(folder: Path) -> None:
    path = folder / "tabsira-mock-v1.json"
    path.write_text(library.dumps(mock_file()) + "\n", encoding="utf-8")
    photos = library.photos(folder / library.PHOTOS_NAME)
    kept = body_of(insight())
    await photos.put("1", library_entry(kept))
    await photos.put("2", library_entry(None, "people"))
    options = PatchOptions(path, frozenset({1, 2}), withdraw="review: unrelated pairing")
    assert await process.patch_stage(options, settings(), Fakes().services()) == 0
    first, second, _ = read(path)["images"]
    assert (first["insight"], second["insight"]) == (None, None)
    entries = read(folder / library.PHOTOS_NAME)["photos"]
    assert entries["1"]["outcome"] == library.WITHDRAWN
    assert entries["1"]["insight"] is None
    assert entries["1"]["withdrawn_insight"] == kept
    assert entries["1"]["withdrawn_reason"] == "review: unrelated pairing"
    # A photo with no kept insight is left as the library has it.
    assert entries["2"]["outcome"] == "people"
    assert "withdrawn_reason" not in entries["2"]
    report = read(folder / patch_module.PATCH_REPORT_NAME)
    assert {c["photo"]: c["outcome"] for c in report["photos"]} == {1: "withdrawn", 2: "people"}


async def test_a_patch_that_changes_nothing_keeps_every_byte(folder: Path) -> None:
    path = folder / "tabsira-mock-v1.json"
    path.write_text(library.dumps(mock_file()) + "\n", encoding="utf-8")
    photos = library.photos(folder / library.PHOTOS_NAME)
    await photos.put("1", library_entry(body_of(insight())))
    before = path.read_bytes()
    await process.patch_stage(PatchOptions(path, frozenset({1})), settings(), Fakes().services())
    assert path.read_bytes() == before


async def test_a_new_scene_alone_is_a_change(folder: Path) -> None:
    path = folder / "tabsira-mock-v1.json"
    path.write_text(library.dumps(mock_file()) + "\n", encoding="utf-8")
    photos = library.photos(folder / library.PHOTOS_NAME)
    scene = {"labels": ["cat", "window"], "ar": "قطة ونافذة"}
    await photos.put("1", library_entry(body_of(insight()), scene=scene))
    await process.patch_stage(PatchOptions(path, frozenset({1})), settings(), Fakes().services())
    assert read(path)["images"][0]["scene"] == scene
    report = read(folder / patch_module.PATCH_REPORT_NAME)["photos"][0]
    assert (report["result"], report["scene_changed"]) == ("replaced", True)


async def test_a_photo_the_library_lacks_is_refused_and_nothing_is_written(
    folder: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_file(folder)
    before = path.read_bytes()
    photos = library.photos(folder / library.PHOTOS_NAME)
    await photos.put("1", library_entry(body_of(insight())))
    options = PatchOptions(path, frozenset({1, 5}))
    assert await process.patch_stage(options, settings(), Fakes().services()) == 2
    assert "5" in capsys.readouterr().out
    assert path.read_bytes() == before
    assert not (folder / patch_module.PATCH_REPORT_NAME).exists()


async def test_a_patched_file_that_fails_the_checks_is_not_written(
    folder: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_file(folder)
    before = path.read_bytes()
    await patch_library(folder)
    fakes = Fakes()
    fakes.problems = ["evidence missing from the store for placepix 1"]
    options = PatchOptions(path, frozenset({1}))
    assert await process.patch_stage(options, settings(), fakes.services()) == 1
    assert path.read_bytes() == before
    assert read(folder / patch_module.PATCH_REPORT_NAME)["checks"] == fakes.problems
    assert "was not patched" in capsys.readouterr().out
    # The library's marks stay as they were: nothing was patched.
    assert read(folder / library.PHOTOS_NAME)["photos"]["1"]["insight_at"] == "2026-10-05T18:00:00Z"


async def test_the_texts_of_the_patched_photos_are_written_again_and_only_those(
    folder: Path,
) -> None:
    fakes = Fakes()
    path = write_file(folder)
    await process.texts_stage(TextOptions(path), settings(), fakes.services())
    # Written a minute ago, so the second the patch runs in does not matter.
    texts = library.texts(folder / library.TEXTS_NAME)
    for entry in texts.entries.values():
        entry["written_at"] = "2026-10-05T18:00:00Z"
    await texts.save()
    await patch_library(folder)
    await process.patch_stage(PatchOptions(path, frozenset({1})), settings(), fakes.services())
    fakes.briefs.clear()
    await process.texts_stage(TextOptions(path), settings(), fakes.services())
    # The post and the sponsor's note of photo 1; photo 2 was not listed, so its post stays.
    assert sorted(brief.post for brief in fakes.briefs) == ["p1", "sponsor:i1"]
