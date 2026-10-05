"""Decision 63: one own scan for a guest, a completed profile for an account."""

from __future__ import annotations

from sqlalchemy import select, update

from src.models import Scan, ScanStatus
from tests.scans.conftest import make_account, photo, sign_in


async def scan(client):
    return await client.post("/scans", files={"image": ("a.jpg", photo(), "image/jpeg")})


async def test_a_guest_has_one_own_scan_and_the_second_asks_for_an_account(browser, store):
    first = await scan(browser)
    second = await scan(browser)

    assert first.status_code == 202
    assert second.status_code == 403
    assert second.json()["error"] == "account_required"
    async with store() as db:
        assert len((await db.scalars(select(Scan))).all()) == 1


async def test_the_rain_tutorial_never_counts_as_an_own_scan(browser, store):
    assert (await browser.post("/tutorial/rain/insights/drop")).status_code in (200, 201)

    assert (await scan(browser)).status_code == 202


async def test_a_scan_that_failed_delivered_nothing_and_leaves_the_guests_one_scan(browser, store):
    assert (await scan(browser)).status_code == 202
    async with store() as db:
        await db.execute(update(Scan).values(status=ScanStatus.FAILED, error_code="X"))
        await db.commit()

    assert (await scan(browser)).status_code == 202


async def test_signing_in_ends_the_limit_because_the_scan_moves_to_the_account(browser, store):
    user = await make_account(store)
    assert (await scan(browser)).status_code == 202
    assert (await scan(browser)).status_code == 403

    await sign_in(browser)

    assert (await scan(browser)).status_code == 202
    async with store() as db:
        owners = (await db.scalars(select(Scan.user_id))).all()
    assert owners == [user.id, user.id]


async def test_an_account_without_a_completed_profile_cannot_scan(browser, store):
    await make_account(store, profile_done=False)
    await sign_in(browser)

    refused = await scan(browser)

    assert refused.status_code == 403
    assert refused.json()["error"] == "profile_required"
    async with store() as db:
        assert (await db.scalars(select(Scan))).all() == []


async def test_an_account_without_a_completed_profile_cannot_use_the_chat(browser, store):
    await make_account(store, profile_done=False)
    await sign_in(browser)
    kept = (await browser.post("/tutorial/rain/insights/drop")).json()

    refused = await browser.post(
        f"/insights/{kept['id']}/chat", json={"message": "ما المطر؟", "idempotencyKey": "key-0001"}
    )

    assert refused.status_code == 403
    assert refused.json()["error"] == "profile_required"


async def test_a_guest_is_not_held_by_the_profile_gate_on_the_chat(browser, model):
    kept = (await browser.post("/tutorial/rain/insights/drop")).json()
    model.answers.append({"level": "a", "asks_for_new_text": False, "answer": "جواب قصير."})

    answered = await browser.post(
        f"/insights/{kept['id']}/chat", json={"message": "ما المطر؟", "idempotencyKey": "key-0001"}
    )

    assert answered.status_code == 200


async def test_the_gate_does_not_tell_whether_an_insight_exists(browser, store):
    await make_account(store, profile_done=False)
    await sign_in(browser)

    missing = await browser.post(
        "/insights/123456/chat", json={"message": "ما المطر؟", "idempotencyKey": "key-0001"}
    )

    assert missing.status_code == 404


async def test_completing_the_profile_opens_the_scan(browser, store):
    await make_account(store, profile_done=False)
    await sign_in(browser)
    assert (await scan(browser)).status_code == 403

    done = await browser.patch(
        "/profile",
        json={
            "complete_profile": True,
            "goals": [],
            "knowledge_level": "unknown",
            "age_range": "unknown",
            "religious_background": "unknown",
            "gender": "unknown",
        },
    )

    assert done.status_code == 200
    assert (await scan(browser)).status_code == 202
