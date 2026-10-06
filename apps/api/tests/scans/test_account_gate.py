"""Decision 64: one own scan for a guest, a completed profile for an account."""

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


async def test_a_guest_cannot_use_the_chat_of_its_own_scan(browser, store, flow_settings):
    from tests.scans.builders import insight_row, scan_row
    from tests.scans.conftest import as_guest

    owner = await as_guest(browser, store, flow_settings)
    async with store() as db:
        row = scan_row(owner, status="done")
        db.add(row)
        await db.flush()
        insight = insight_row(owner, scan_id=row.id)
        db.add(insight)
        await db.commit()

    refused = await browser.post(
        f"/insights/{insight.id}/chat", json={"message": "ما المطر؟", "idempotencyKey": "key-0001"}
    )

    assert refused.status_code == 403
    assert refused.json()["error"] == "account_required"


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


async def test_looking_again_needs_the_completed_profile_too(browser, flow_app, store):
    from sqlalchemy import update

    from src.models import Profile
    from tests.scans.jobs import run_queued

    user = await make_account(store)
    await sign_in(browser)
    body = (await scan(browser)).json()
    await run_queued(flow_app, store)
    async with store() as db:
        await db.execute(
            update(Profile).where(Profile.user_id == user.id).values(profile_completed_at=None)
        )
        await db.commit()

    focus = await browser.post(f"/scans/{body['id']}/focus", json={"entity_id": "e1"})
    clarify = await browser.post(f"/scans/{body['id']}/clarify", json={"answer": "نعم"})

    assert [(r.status_code, r.json()["error"]) for r in (focus, clarify)] == [
        (403, "profile_required")
    ] * 2


async def test_an_account_with_an_own_insight_is_no_longer_offered_the_tutorial(
    browser, flow_app, store
):
    from src.models import Insight, InsightOrigin
    from tests.scans.jobs import run_queued

    await make_account(store)
    await sign_in(browser)
    assert (await browser.get("/auth/me")).json()["has_own_insight"] is False
    assert (await browser.post("/tutorial/rain/insights/drop")).status_code == 200
    # A kept tutorial copy is not an insight of its own.
    assert (await browser.get("/auth/me")).json()["has_own_insight"] is False

    assert (await scan(browser)).status_code == 202
    await run_queued(flow_app, store)
    async with store() as db:
        origins = (await db.scalars(select(Insight.origin))).all()
    assert InsightOrigin.SCAN in origins

    assert (await browser.get("/auth/me")).json()["has_own_insight"] is True
    closed = await browser.post("/tutorial/rain/insights/planting")
    assert closed.status_code == 403
    assert closed.json()["error"] == "tutorial_closed"
    # The landing stays public: the visitors' example is not taken away.
    assert (await browser.get("/tutorial/rain")).status_code == 200


async def test_a_guest_keeps_the_tutorial_after_its_own_scan(browser, flow_app, store):
    from tests.scans.jobs import run_queued

    assert (await scan(browser)).status_code == 202
    await run_queued(flow_app, store)

    assert (await browser.post("/tutorial/rain/insights/drop")).status_code == 200
