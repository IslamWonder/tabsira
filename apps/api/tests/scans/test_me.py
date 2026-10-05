"""`GET /me/progress`: what recorded practice adds up to, in the learner's own day."""

from __future__ import annotations

from datetime import timedelta

from src import clock
from src.messages import messages_for
from src.models import ActionState, ChatMessage, ChatStatus, InsightOrigin, ScanOutcome, Treasure
from src.owner import Owner
from tests.scans.builders import insight_row, scan_row
from tests.scans.conftest import as_guest


async def test_a_newcomer_starts_at_the_first_rank_with_every_badge_locked(browser):
    response = await browser.get("/me/progress")

    body = response.json()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert body["timezone"] == "UTC"
    assert (body["rank"]["id"], body["rank"]["title"], body["rank"]["looks"]) == (
        "nazir",
        "ناظر",
        0,
    )
    assert body["rank"]["next"] == {"id": "mutaammil", "title": "متأمّل", "minimum": 3}
    assert body["streak"]["current"] == body["streak"]["best"] == 0
    assert len(body["streak"]["days"]) == 7
    assert body["daily_quest"]["title"] == "بصيرة اليوم"
    assert [step["done"] for step in body["daily_quest"]["steps"]] == [False, False]
    assert body["sky"] == {"count": 0, "stars": []}
    assert len(body["badges"]) == 12
    assert not any(badge["earned"] for badge in body["badges"])
    assert body["disclaimer"] == messages_for().practice_disclaimer
    for forbidden in ("leaderboard", "rank_among", "percentile", "iman", "hasanat"):
        assert forbidden not in response.text


async def test_recorded_practice_moves_the_rank_streak_quest_sky_and_badges(
    browser, store, flow_settings, moving_clock
):
    owner = await as_guest(browser, store, flow_settings)
    async with store() as db:
        for day in range(3):
            scan = scan_row(
                owner,
                status="done",
                outcome=ScanOutcome.INSIGHTS,
                finished_at=clock.utcnow() - timedelta(days=2 - day),
            )
            db.add(scan)
            await db.flush()
        insight = insight_row(
            owner,
            scan_id=scan.id,
            completed_at=clock.utcnow(),
            action_state=ActionState.DONE,
            action_at=clock.utcnow(),
        )
        drop = insight_row(
            owner,
            origin=InsightOrigin.TUTORIAL,
            tutorial_scene="rain-1.0",
            tutorial_slug="drop",
            completed_at=clock.utcnow(),
            why={"concept": "الغرس"},
        )
        db.add_all([insight, drop])
        await db.flush()
        db.add(
            ChatMessage(
                insight_id=insight.id,
                idempotency_key="key-0001",
                status=ChatStatus.ANSWERED,
                question="؟",
                answer="جواب",
                level="a",
                kind="answer",
                answered_at=clock.utcnow(),
            )
        )
        db.add(
            Treasure(
                insight_id=insight.id,
                place_id=await _place(db, owner),
                kind="alternative",
                quran_surah=6,
                quran_ayah=99,
                learning_unit_id="T01_03",
                learning_path_version="tabsira-masar-1.0",
                revealed_at=clock.utcnow(),
            )
        )
        await db.commit()

    body = (await browser.get("/me/progress", params={"tz": "Asia/Riyadh"})).json()

    assert body["timezone"] == "Asia/Riyadh"
    assert (body["rank"]["id"], body["rank"]["looks"], body["rank"]["progress"]) == (
        "mutaammil",
        3,
        0.0,
    )
    assert (body["streak"]["current"], body["streak"]["best"]) == (3, 3)
    assert body["daily_quest"]["done"] is True
    assert body["daily_quest"]["days_done"] == 1
    assert [star["concept"] for star in body["sky"]["stars"]] == ["الإحياء", "الغرس"]
    assert [
        [(item["id"], item["title"]) for item in star["insights"]] for star in body["sky"]["stars"]
    ] == [[(str(insight.id), insight.title)], [(str(drop.id), drop.title)]]
    assert body["counts"] == {
        "looks": 3,
        "completed": 2,
        "actions_done": 1,
        "places": 1,
        "treasures": 1,
        "questions": 1,
    }
    earned = {badge["id"] for badge in body["badges"] if badge["earned"]}
    assert earned == {
        "first-look",
        "first-action",
        "first-place",
        "first-treasure",
        "asked",
        "streak-3",
        "daily-quest",
    }


async def _place(db, owner: Owner):
    from src.models import WorldPlace

    place = WorldPlace(**owner.columns(), region_id="T01", regions_version="1.0")
    db.add(place)
    await db.flush()
    return place.id


async def test_an_unknown_time_zone_is_refused(browser):
    for tz in ("Mars/Olympus", "../etc/passwd"):
        response = await browser.get("/me/progress", params={"tz": tz})
        assert (response.status_code, response.json()["error"]) == (422, "VALIDATION_ERROR")
