"""A guest's saved learning joins the account at sign-in; export and deletion cover all of it."""

from __future__ import annotations

from redis.exceptions import RedisError
from sqlalchemy import select

from src.models import EvidenceExposure, Guest, Insight, Scan, User
from src.scans import buffer
from tests.scans.conftest import make_account, photo, sign_in


async def test_signing_in_merges_what_the_browser_saved_as_a_guest(browser, store, flow_settings):
    user = await make_account(store)
    kept = (await browser.post("/tutorial/rain/insights/drop")).json()
    await browser.post(f"/insights/{kept['id']}/complete")
    scan = (await browser.post("/scans", files={"image": ("a.jpg", photo(), "image/jpeg")})).json()

    response = await browser.post(
        "/auth/login", json={"email": user.email, "password": "correct horse battery"}
    )

    cookies = response.headers.get_list("set-cookie")
    assert any(cookie.startswith(f"{flow_settings.guest_cookie_name}=") for cookie in cookies)
    assert any("Max-Age=0" in c for c in cookies if c.startswith(flow_settings.guest_cookie_name))
    async with store() as db:
        assert (await db.scalars(select(Guest))).all() == []
        assert (await db.get(Insight, int(kept["id"]))).user_id == user.id
        assert (await db.get(Scan, int(scan["id"]))).user_id == user.id
        assert (await db.scalars(select(EvidenceExposure.user_id))).all() == [user.id]
    assert (await browser.get(f"/insights/{kept['id']}")).status_code == 200
    world = (await browser.get("/world")).json()
    assert [place["region_id"] for place in world["places"]] == ["T01"]


async def test_the_export_holds_everything_the_learner_saved_and_never_a_photo(
    browser, store, model
):
    await make_account(store)
    await sign_in(browser)
    kept = (await browser.post("/tutorial/rain/insights/drop")).json()
    model.answers.append({"level": "a", "asks_for_new_text": False, "answer": "جواب قصير."})
    await browser.post(
        f"/insights/{kept['id']}/chat", json={"message": "ما المطر؟", "idempotencyKey": "key-0001"}
    )
    await browser.post(f"/insights/{kept['id']}/complete")
    await browser.post("/scans", files={"image": ("a.jpg", photo(), "image/jpeg")})

    learning = (await browser.get("/account/export")).json()["learning"]

    assert set(learning) == {
        "scans",
        "insights",
        "chat_messages",
        "places",
        "treasures",
        "learner_units",
        "exposures",
    }
    assert [scan["source"] for scan in learning["scans"]] == ["upload"]
    assert "image" not in learning["scans"][0]
    assert [insight["tutorial_slug"] for insight in learning["insights"]] == ["drop"]
    assert [message["answer"] for message in learning["chat_messages"]] == ["جواب قصير."]
    assert [place["region_id"] for place in learning["places"]] == ["T01"]
    assert [unit["unit_id"] for unit in learning["learner_units"]] == ["T01_06"]
    assert [exposure["quran_surah"] for exposure in learning["exposures"]] == [30]
    assert learning["treasures"] == []


async def test_deleting_the_account_deletes_its_learning_and_its_kept_photos(browser, store, redis):
    user = await make_account(store)
    await sign_in(browser)
    kept = (await browser.post("/tutorial/rain/insights/drop")).json()
    await browser.post(f"/insights/{kept['id']}/complete")
    scan_id = int(
        (await browser.post("/scans", files={"image": ("a.jpg", photo(), "image/jpeg")})).json()[
            "id"
        ]
    )

    response = await browser.delete("/account")

    assert response.status_code == 204
    assert not await buffer.kept(redis, scan_id, buffer.Copy.FULL)
    async with store() as db:
        assert await db.get(User, user.id) is None
        for model in (Scan, Insight, EvidenceExposure):
            assert (await db.scalars(select(model))).all() == []


async def test_a_redis_that_is_down_does_not_stop_a_deletion(browser, store, redis, monkeypatch):
    await make_account(store)
    await sign_in(browser)
    await browser.post("/scans", files={"image": ("a.jpg", photo(), "image/jpeg")})

    async def down(*_args):
        message = "down"
        raise RedisError(message)

    monkeypatch.setattr(buffer, "drop", down)

    response = await browser.delete("/account")

    assert response.status_code == 204
    async with store() as db:
        assert (await db.scalars(select(Scan))).all() == []
