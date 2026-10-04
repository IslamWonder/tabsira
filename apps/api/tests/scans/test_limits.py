"""Scans, chat answers and kept tutorial insights cost model calls: each is limited per address."""

from __future__ import annotations

from src.services.window_limiter import AddressLimits
from tests.scans.conftest import as_guest, photo
from tests.scans.test_chat import an_insight, ask, said


async def test_scans_are_limited_per_address_before_any_guest_is_made(
    browser, flow_app, store, queue, flow_settings
):
    flow_app.state.scan_limits = AddressLimits(1, 100, 3600)

    first = await browser.post("/scans", files={"image": ("a.jpg", photo(), "image/jpeg")})
    browser.cookies.clear()
    second = await browser.post("/scans", files={"image": ("a.jpg", photo(), "image/jpeg")})

    assert first.status_code == 202
    assert (second.status_code, second.json()["error"]) == (429, "RATE_LIMITED")
    assert int(second.headers["retry-after"]) >= 1
    assert flow_settings.guest_cookie_name not in second.headers.get("set-cookie", "")
    assert len(queue.runs) == 1


async def test_focus_and_clarify_share_the_scan_budget(browser, flow_app, store, flow_settings):
    await as_guest(browser, store, flow_settings)
    flow_app.state.scan_limits = AddressLimits(0, 100, 3600)

    for path in ("/scans/1/focus", "/scans/1/clarify"):
        response = await browser.post(path, json={"entity_id": "e1", "answer": "مطر"})
        assert (response.status_code, response.json()["error"]) == (429, "RATE_LIMITED")


async def test_chat_answers_are_limited_per_address(browser, flow_app, store, flow_settings, model):
    insight_id = await an_insight(browser, store, flow_settings)
    flow_app.state.chat_limits = AddressLimits(1, 100, 3600)
    model.answers.append(said())

    first = await ask(browser, insight_id, key="key-0001")
    second = await ask(browser, insight_id, key="key-0002")

    assert first.status_code == 200
    assert (second.status_code, second.json()["error"]) == (429, "RATE_LIMITED")


async def test_keeping_tutorial_insights_is_limited_per_address(browser, flow_app, store):
    flow_app.state.keep_limits = AddressLimits(1, 100, 3600)

    first = await browser.post("/tutorial/rain/insights/drop")
    second = await browser.post("/tutorial/rain/insights/planting")

    assert first.status_code == 200
    assert (second.status_code, second.json()["error"]) == (429, "RATE_LIMITED")
