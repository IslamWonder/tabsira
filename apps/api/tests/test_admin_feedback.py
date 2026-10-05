"""The readers' ratings in the admin: listed, filtered, marked reviewed, never edited."""

from __future__ import annotations

from sqlalchemy import select

from src import clock
from src.models import AuditAction, FeedbackState, InsightFeedback
from src.owner import Owner
from tests.scans.builders import insight_row, scan_row
from tests.support_admin import audit_rows, csrf_of


async def rated(db_session, owner_id, *, helpful: bool) -> InsightFeedback:
    owner = Owner(user_id=owner_id)
    scan = scan_row(owner, status="done")
    db_session.add(scan)
    await db_session.flush()
    insight = insight_row(owner, scan_id=scan.id)
    db_session.add(insight)
    await db_session.flush()
    row = InsightFeedback(
        insight_id=insight.id,
        helpful=helpful,
        reasons=[] if helpful else ["wrong_text"],
        note=None if helpful else "النص بعيد عن المشهد",
        state=FeedbackState.OPEN,
        updated_at=clock.utcnow(),
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def mark(http, pks):
    return await http.post(
        f"/admin/insight-feedback/action/reviewed?pks={pks}",
        data={"csrf_token": await csrf_of(http)},
    )


async def test_the_ratings_are_listed_with_their_reasons_and_notes(admin, db_session):
    http, me = admin
    await rated(db_session, me.id, helpful=False)

    page = await http.get("/admin/insight-feedback/list")

    assert page.status_code == 200
    for expected in ("wrong_text", "النص بعيد عن المشهد", "open"):
        assert expected in page.text


async def test_marking_reviewed_closes_the_ticked_ratings_and_is_audited(admin, db_session):
    http, me = admin
    first = await rated(db_session, me.id, helpful=False)
    second = await rated(db_session, me.id, helpful=True)

    response = await mark(http, f"{first.id}")

    assert response.status_code == 303
    states = {
        row.id: row.state for row in (await db_session.scalars(select(InsightFeedback))).all()
    }
    await db_session.refresh(first)
    await db_session.refresh(second)
    assert (first.state, second.state) == (FeedbackState.REVIEWED, FeedbackState.OPEN)
    assert len(states) == 2
    row = [r for r in await audit_rows(db_session) if r.action is AuditAction.BULK_ACTION][-1]
    assert row.model == "insight-feedback"


async def test_marking_needs_a_selection(admin, db_session):
    http, me = admin
    await rated(db_session, me.id, helpful=False)

    response = await mark(http, "")

    assert "error=Select+at+least+one+rating." in response.headers["location"]


async def test_a_rating_cannot_be_created_edited_or_deleted(admin, db_session):
    http, me = admin
    row = await rated(db_session, me.id, helpful=False)

    assert (await http.get("/admin/insight-feedback/create")).status_code in {403, 404}
    assert (await http.get(f"/admin/insight-feedback/edit/{row.id}")).status_code in {403, 404}
