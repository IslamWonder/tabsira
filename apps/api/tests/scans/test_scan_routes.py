"""The scan routes: a photo or its address in, a queued job out, its progress, its owner only."""

from __future__ import annotations

import pytest
from redis.exceptions import RedisError
from sqlalchemy import select

from src.models import Scan, ScanOutcome, ScanStatus
from src.pipeline.engine import EngineResult, EngineStatus
from src.scans import buffer, progress
from src.scans.fetch import FetchError, FetchRefusal
from tests.scans.conftest import make_account, photo, sign_in
from tests.scans.jobs import run_queued, scene_answer

URL = "https://photos.example/rain.jpg"


async def upload(client, data: bytes | None = None, name: str = "image"):
    return await client.post(
        "/scans", files={name: ("rain.jpg", data if data is not None else photo(), "image/jpeg")}
    )


async def a_scan(browser) -> dict:
    response = await upload(browser)
    assert response.status_code == 202, response.text
    return response.json()


async def test_an_upload_starts_a_scan_for_a_new_guest_and_answers_at_once(
    browser, store, redis, queue, flow_settings
):
    response = await upload(browser)

    body = response.json()
    assert response.status_code == 202
    assert response.headers["cache-control"] == "no-store"
    assert flow_settings.guest_cookie_name in response.headers["set-cookie"]
    assert (body["status"], body["source"], body["run"], body["engine"]) == (
        "queued",
        "upload",
        1,
        "pipeline",
    )
    assert body["engine_label"] is None
    # No photo is shown back before the sensitivity verdict.
    assert body["image"] == {"available": False, "width": 96, "height": 64, "url": None}
    assert (await browser.get(f"/scans/{body['id']}/image")).status_code == 404
    assert body["events_url"] == f"/scans/{body['id']}/events"
    assert body["disclosure"] == "تبصرة أداة مدعومة بالذكاء الاصطناعي، وليست مفتيًا ولا عالمًا"
    # A public id travels as a string: it is beyond the integers JavaScript holds exactly.
    assert isinstance(body["id"], str)
    scan_id = int(body["id"])
    assert queue.runs == [(scan_id, 1)]
    assert [event.event for event in await progress.replay(redis, scan_id)] == ["queued"]
    assert await buffer.kept(redis, scan_id, buffer.Copy.MODEL)
    async with store() as db:
        scan = await db.get(Scan, scan_id)
        assert scan.guest_key is not None
        assert scan.user_id is None

    again = await upload(browser)
    assert "set-cookie" not in again.headers
    async with store() as db:
        assert (await db.get(Scan, int(again.json()["id"]))).guest_key == scan.guest_key


async def test_an_address_is_fetched_by_the_server(browser, fetcher, store):
    fetcher.answers[URL] = photo()

    response = await browser.post("/scans", json={"url": URL})

    assert response.status_code == 202
    assert response.json()["source"] == "url"
    assert fetcher.asked == [URL]


@pytest.mark.parametrize(
    ("refusal", "status", "code"),
    [
        (FetchRefusal.FORBIDDEN_ADDRESS, 400, "IMAGE_URL_REFUSED"),
        (FetchRefusal.INVALID_URL, 400, "IMAGE_URL_REFUSED"),
        (FetchRefusal.TIMEOUT, 422, "IMAGE_FETCH_FAILED"),
        (FetchRefusal.NOT_AN_IMAGE, 422, "IMAGE_FETCH_FAILED"),
        (FetchRefusal.TOO_LARGE, 413, "IMAGE_TOO_LARGE"),
    ],
)
async def test_an_address_that_cannot_be_used_says_why(browser, fetcher, refusal, status, code):
    fetcher.answers[URL] = FetchError(refusal, "no")

    response = await browser.post("/scans", json={"url": URL})

    assert (response.status_code, response.json()["error"]) == (status, code)


@pytest.mark.parametrize(
    ("data", "status", "code"),
    [
        (b"", 400, "IMAGE_EMPTY"),
        (b"not an image at all", 415, "IMAGE_UNSUPPORTED"),
        (photo(8, 8), 400, "IMAGE_TOO_SMALL"),
        (b"\xff\xd8\xff" + b"\x00" * 64, 400, "IMAGE_INVALID"),
    ],
)
async def test_a_photo_that_cannot_be_used_says_why(browser, queue, data, status, code):
    response = await upload(browser, data)

    assert (response.status_code, response.json()["error"]) == (status, code)
    assert queue.runs == []


async def test_a_photo_over_the_limit_is_refused(browser, flow_app, make_settings):
    flow_app.state.settings = make_settings(image_max_bytes=1000)

    declared = await browser.post(
        "/scans",
        content=b"x" * 10,
        headers={"content-type": "image/jpeg", "content-length": "99999"},
    )
    read = await upload(browser, photo(400, 400))

    assert (declared.status_code, declared.json()["error"]) == (413, "IMAGE_TOO_LARGE")
    assert (read.status_code, read.json()["error"]) == (413, "IMAGE_TOO_LARGE")


async def test_a_request_that_is_neither_a_photo_nor_an_address_is_refused(browser):
    wrong_type = await browser.post("/scans", content=b"x", headers={"content-type": "text/plain"})
    wrong_json = await browser.post("/scans", json={"link": URL})
    no_field = await upload(browser, name="file")

    assert (wrong_type.status_code, wrong_type.json()["error"]) == (415, "UNSUPPORTED_MEDIA_TYPE")
    assert (wrong_json.status_code, wrong_json.json()["error"]) == (422, "VALIDATION_ERROR")
    assert (no_field.status_code, no_field.json()["error"]) == (400, "IMAGE_EMPTY")


async def test_a_redis_that_is_down_saves_nothing(browser, store, monkeypatch):
    async def down(*_args, **_kwargs):
        message = "down"
        raise RedisError(message)

    monkeypatch.setattr(buffer, "put", down)

    response = await upload(browser)

    assert (response.status_code, response.json()["error"]) == (503, "QUEUE_UNAVAILABLE")
    async with store() as db:
        assert (await db.scalars(select(Scan))).all() == []


async def test_a_queue_that_is_down_fails_the_scan_honestly(browser, store, queue):
    queue.broken = True

    response = await upload(browser)

    assert (response.status_code, response.json()["error"]) == (503, "QUEUE_UNAVAILABLE")
    async with store() as db:
        scan = (await db.scalars(select(Scan))).one()
    assert (scan.status, scan.error_code) == (ScanStatus.FAILED, "QUEUE_UNAVAILABLE")


async def test_only_the_owner_reaches_a_scan(browser, other, flow_app, store):
    body = await a_scan(browser)
    path = f"/scans/{body['id']}"
    await make_account(store)
    await sign_in(other)

    assert (await browser.get(path)).json()["id"] == body["id"]
    for client_path in (path, f"{path}/image", f"{path}/events"):
        response = await other.get(client_path)
        assert (response.status_code, response.json()["error"]) == (404, "NOT_FOUND")
    browser.cookies.clear()
    assert (await browser.get(path)).status_code == 404
    assert (await browser.get(f"/scans/{7_314_159_265_358_979_323}")).status_code == 404
    for malformed in ("abc", "0", "-5", str(2**63)):
        assert (await browser.get(f"/scans/{malformed}")).status_code == 422


async def test_the_owner_sees_the_photo_while_it_is_kept(
    browser, flow_app, store, redis, monkeypatch
):
    body = await a_scan(browser)
    path = f"/scans/{body['id']}/image"
    await run_queued(flow_app, store)
    assert (await browser.get(f"/scans/{body['id']}")).json()["image"] == {
        "available": True,
        "width": 96,
        "height": 64,
        "url": path,
    }

    shown = await browser.get(path)
    assert shown.headers["content-type"] == "image/jpeg"
    assert shown.headers["cache-control"] == "no-store"
    assert shown.content == await buffer.get(
        redis, int(body["id"]), buffer.Copy.FULL, key=buffer.photo_key(flow_app.state.settings)
    )

    async def broken(*_args):
        message = "down"
        raise RedisError(message)

    monkeypatch.setattr(redis, "exists", broken)
    assert (await browser.get(f"/scans/{body['id']}")).json()["image"]["available"] is False
    monkeypatch.undo()
    await buffer.drop(redis, int(body["id"]))
    gone = await browser.get(path)
    assert (gone.status_code, gone.json()["error"]) == (404, "ASSET_MISSING")


async def test_a_finished_scan_shows_its_scene_insights_and_progress(
    browser, flow_app, store, redis, flow_settings
):
    body = await a_scan(browser)
    await run_queued(flow_app, store)

    scan = (await browser.get(f"/scans/{body['id']}")).json()
    stream = await browser.get(f"/scans/{body['id']}/events")
    resumed = await browser.get(f"/scans/{body['id']}/events", headers={"Last-Event-ID": "7"})

    assert (scan["status"], scan["outcome"]) == ("done", "insights")
    assert scan["description"] == "نبتة صغيرة تحت المطر"
    assert scan["entities"][0]["label_arabic"] == "نبتة"
    assert [insight["relation_label"] for insight in scan["insights"]] == ["تذكير عام"]
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert stream.headers["cache-control"] == "no-store"
    names = [
        line.removeprefix("event: ")
        for line in stream.text.splitlines()
        if line.startswith("event: ")
    ]
    assert names[0] == "queued"
    assert names[-1] == "done"
    assert "id: 1\r\n" in stream.text or "id: 1\n" in stream.text
    # Ten events: queued, the three stages of the scene and of the simulation, done.
    assert [line for line in resumed.text.splitlines() if line.startswith("id: ")] == [
        "id: 8",
        "id: 9",
        "id: 10",
    ]


async def test_a_finished_scan_whose_events_expired_answers_from_the_database(
    browser, flow_app, store, redis
):
    body = await a_scan(browser)
    scan_id = int(body["id"])
    await run_queued(flow_app, store, engine=_Static(EngineStatus.MODEL_UNAVAILABLE))
    await redis.delete(progress.events_key(scan_id))

    failed = await browser.get(f"/scans/{body['id']}/events")

    assert "event: failed" in failed.text
    assert "MODEL_UNAVAILABLE" in failed.text
    async with store() as db:
        scan = await db.get(Scan, scan_id)
        scan.status, scan.outcome, scan.error_code = ScanStatus.DONE, None, None
        await db.commit()
    done = await browser.get(f"/scans/{body['id']}/events")
    assert "event: done" in done.text
    assert "no_relevant_evidence" in done.text


class _Static:
    def __init__(self, status: EngineStatus, question: str | None = None) -> None:
        self.status = status
        self.question = question

    async def propose(self, request, on_stage=None):
        return EngineResult(status=self.status, clarification_question=self.question)


async def test_focusing_runs_the_engine_again_on_the_same_scene(browser, flow_app, store, queue):
    body = await a_scan(browser)
    path = f"/scans/{body['id']}"
    busy = await browser.post(f"{path}/focus", json={"entity_id": "e1"})
    await run_queued(flow_app, store)

    unknown = await browser.post(f"{path}/focus", json={"entity_id": "e9"})
    focused = await browser.post(f"{path}/focus", json={"entity_id": "e1"})
    await run_queued(flow_app, store, answers=[])
    drawn = await browser.post(
        f"{path}/focus",
        json={"box": {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.3}, "label": "ورقة"},
    )

    assert (busy.status_code, busy.json()["error"]) == (409, "SCAN_BUSY")
    assert (unknown.status_code, unknown.json()["error"]) == (422, "VALIDATION_ERROR")
    assert (focused.status_code, focused.json()["run"], focused.json()["status"]) == (
        202,
        2,
        "queued",
    )
    assert drawn.json()["run"] == 3
    assert queue.runs == [(int(body["id"]), 3)]
    async with store() as db:
        scan = await db.get(Scan, int(body["id"]))
    assert scan.focus == {"box": {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.3}, "label": "ورقة"}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"entity_id": "e1", "box": {"x": 0, "y": 0, "width": 0.1, "height": 0.1}},
        {"box": {"x": 0.8, "y": 0, "width": 0.5, "height": 0.1}},
        {"box": {"x": 0.1, "y": 0.8, "width": 0.1, "height": 0.5}},
        {"box": {"x": 0.1, "y": 0.1, "width": 0, "height": 0.1}},
    ],
)
async def test_a_focus_names_one_thing_or_one_box_inside_the_photo(browser, body):
    scan = await a_scan(browser)

    response = await browser.post(f"/scans/{scan['id']}/focus", json=body)

    assert response.status_code == 422


async def test_a_scan_whose_scene_was_never_understood_cannot_be_focused(browser, flow_app, store):
    scan = await a_scan(browser)
    await run_queued(flow_app, store, answers=[_failure()])

    response = await browser.post(f"/scans/{scan['id']}/focus", json={"entity_id": "e1"})

    assert (response.status_code, response.json()["error"]) == (409, "ASSET_MISSING")


def _failure():
    from src.ai.errors import AiCallError, AiErrorCode

    return AiCallError(AiErrorCode.NETWORK, "down")


async def test_the_answer_to_the_scan_question_runs_the_engine_again(browser, flow_app, store):
    scan = await a_scan(browser)
    path = f"/scans/{scan['id']}"
    early = await browser.post(f"{path}/clarify", json={"answer": "مطر"})
    await run_queued(
        flow_app,
        store,
        answers=[scene_answer(clarification_question="ما الذي يحدث هنا؟")],
    )

    asked = (await browser.get(path)).json()
    answered = await browser.post(f"{path}/clarify", json={"answer": "  مطر على نبتة  "})
    await run_queued(flow_app, store, answers=[])

    assert (early.status_code, early.json()["error"]) == (409, "SCAN_BUSY")
    assert (asked["outcome"], asked["clarification_question"]) == (
        "needs_clarification",
        "ما الذي يحدث هنا؟",
    )
    assert answered.status_code == 202
    async with store() as db:
        stored = await db.get(Scan, int(scan["id"]))
    assert stored.clarification_answer == "مطر على نبتة"
    assert stored.outcome is ScanOutcome.INSIGHTS
    assert (await browser.post(f"{path}/clarify", json={"answer": ""})).status_code == 422
    no_question = await browser.post(f"{path}/clarify", json={"answer": "مطر"})
    assert (no_question.status_code, no_question.json()["error"]) == (409, "CONFLICT")


async def test_a_sensitive_scene_never_shows_its_photo(browser, flow_app, store):
    scan = await a_scan(browser)
    await run_queued(flow_app, store, answers=[scene_answer(sensitive=["violence"])])

    body = (await browser.get(f"/scans/{scan['id']}")).json()
    image = await browser.get(f"/scans/{scan['id']}/image")

    assert body["sensitive"] is True
    assert body["image"] == {"available": False, "width": None, "height": None, "url": None}
    assert body["description"] == "نبتة صغيرة تحت المطر"
    assert (image.status_code, image.json()["error"]) == (404, "ASSET_MISSING")


async def test_the_simulation_is_labelled(browser, flow_app, make_settings):
    flow_app.state.settings = make_settings(scan_engine="demo")

    body = (await upload(browser)).json()

    assert body["engine"] == "demo"
    assert "محاكاة" in body["engine_label"]


async def test_a_running_scan_streams_until_its_run_ends(browser, redis):
    scan = await a_scan(browser)
    await progress.publish(
        redis, int(scan["id"]), "failed", {"run": 1, "code": "SCAN_TIMEOUT"}, ttl=60
    )

    stream = await browser.get(f"/scans/{scan['id']}/events")

    assert [line for line in stream.text.splitlines() if line.startswith("event: ")] == [
        "event: queued",
        "event: failed",
    ]


async def test_the_default_fetcher_goes_through_the_guarded_client(flow_settings, monkeypatch):
    from fastapi import FastAPI
    from starlette.requests import Request

    from src.scans import deps

    seen: list[str] = []

    async def fake_fetch(url, settings, *, client):
        seen.append(url)
        return b"photo"

    monkeypatch.setattr(deps, "fetch_image", fake_fetch)
    fetch = deps.image_fetcher(Request({"type": "http", "app": FastAPI()}), flow_settings)

    assert await fetch(URL) == b"photo"
    assert seen == [URL]
