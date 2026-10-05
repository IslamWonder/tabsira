"""The owner's rating of an insight: PUT /insights/{id}/feedback, its display, export and admin."""

from __future__ import annotations

from sqlalchemy import select

from src.models import FeedbackState, Insight, InsightFeedback, User
from src.owner import Owner
from tests.scans.builders import insight_row, scan_row
from tests.scans.conftest import as_guest, make_account, sign_in

NOT_USEFUL = {
    "helpful": False,
    "reasons": ["wrong_text", "misread_scene"],
    "note": "  الآية بعيدة عن المشهد.  ",
}


async def owned_insight(browser, store, flow_settings) -> str:
    owner = await as_guest(browser, store, flow_settings)
    return await insight_of(store, owner)


async def insight_of(store, owner: Owner) -> str:
    async with store() as db:
        scan = scan_row(owner, status="done")
        db.add(scan)
        await db.flush()
        insight = insight_row(owner, scan_id=scan.id)
        db.add(insight)
        await db.commit()
        return str(insight.id)


async def stored(store, insight_id: str) -> InsightFeedback | None:
    async with store() as db:
        found: InsightFeedback | None = await db.scalar(
            select(InsightFeedback).where(InsightFeedback.insight_id == int(insight_id))
        )
        return found


async def test_the_owner_rates_an_insight_not_useful_with_reasons_and_a_note(
    browser, store, flow_settings
):
    insight_id = await owned_insight(browser, store, flow_settings)

    response = await browser.put(f"/insights/{insight_id}/feedback", json=NOT_USEFUL)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["helpful"], body["reasons"]) == (False, ["wrong_text", "misread_scene"])
    # The note is trimmed; an empty one is no note.
    assert body["note"] == "الآية بعيدة عن المشهد."
    shown = (await browser.get(f"/insights/{insight_id}")).json()["feedback"]
    assert shown == body
    row = await stored(store, insight_id)
    assert row is not None and row.state is FeedbackState.OPEN


async def test_answering_again_replaces_the_rating_and_reopens_it_for_review(
    browser, store, flow_settings
):
    insight_id = await owned_insight(browser, store, flow_settings)
    await browser.put(f"/insights/{insight_id}/feedback", json=NOT_USEFUL)
    async with store() as db:
        row = await db.scalar(select(InsightFeedback))
        assert row is not None
        row.state = FeedbackState.REVIEWED
        await db.commit()

    again = await browser.put(
        f"/insights/{insight_id}/feedback", json={"helpful": True, "note": "   "}
    )

    assert again.json() | {"updated_at": None} == {
        "helpful": True,
        "reasons": [],
        "note": None,
        "updated_at": None,
    }
    async with store() as db:
        rows = (await db.scalars(select(InsightFeedback))).all()
    assert len(rows) == 1
    assert rows[0].state is FeedbackState.OPEN


async def test_an_insight_never_rated_says_so(browser, store, flow_settings):
    insight_id = await owned_insight(browser, store, flow_settings)
    assert (await browser.get(f"/insights/{insight_id}")).json()["feedback"] is None


async def test_a_rating_is_refused_when_it_does_not_hold_together(browser, store, flow_settings):
    insight_id = await owned_insight(browser, store, flow_settings)
    for body in (
        {"helpful": True, "reasons": ["other"]},
        {"helpful": False, "reasons": ["other", "other"]},
        {"helpful": False, "reasons": ["made_up"]},
        {"helpful": False, "note": "x" * 301},
        {"reasons": []},
    ):
        response = await browser.put(f"/insights/{insight_id}/feedback", json=body)
        assert response.status_code == 422, body
    assert await stored(store, insight_id) is None


async def test_nobody_but_the_owner_can_rate(browser, other, store, flow_settings):
    insight_id = await owned_insight(browser, store, flow_settings)
    await as_guest(other, store, flow_settings)

    response = await other.put(f"/insights/{insight_id}/feedback", json=NOT_USEFUL)

    assert response.status_code == 404
    assert await stored(store, insight_id) is None


async def test_the_export_carries_the_ratings_and_they_go_with_the_account(
    browser, store, flow_settings
):
    user = await make_account(store)
    await sign_in(browser)
    insight_id = await insight_of(store, Owner(user_id=user.id))
    await browser.put(f"/insights/{insight_id}/feedback", json=NOT_USEFUL)

    exported = (await browser.get("/account/export")).json()["learning"]["feedback"]
    assert len(exported) == 1
    assert exported[0] | {"updated_at": None} == {
        "insight_id": insight_id,
        "helpful": False,
        "reasons": ["wrong_text", "misread_scene"],
        "note": "الآية بعيدة عن المشهد.",
        "updated_at": None,
    }

    assert (await browser.delete("/account")).status_code == 204
    async with store() as db:
        assert await db.scalar(select(User).where(User.id == user.id)) is None
        assert await db.scalar(select(Insight).where(Insight.id == int(insight_id))) is None
        assert await db.scalar(select(InsightFeedback)) is None
