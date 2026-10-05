"""
The developer panel (v2 §23): one scan's stored trace, in the admin area.

The page shows the scan's status, every stage with its time, the model calls with their
cost, the entities of the verified scene and the insights by their references. It never
shows the photo, the owner, the exact point or the answer a person typed; the scripture
appears by reference only. The audit log names the scan an admin looked at, and the whole
view is gone when the dev_inspector feature is off.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from src import clock
from src.models import AiCall, AuditAction, ScanEvent, ScanOutcome, ScanStatus
from src.owner import Owner
from tests.scans.builders import entity, insight_row, scan_row, scene
from tests.support_admin import audit_rows, browser, sign_in

FORM = "/admin/inspect"
# A detail of the person that must never reach the page.
TYPED_ANSWER = "جوابي الخاص على السؤال"
TYPED_LABEL = "ما أشرت إليه بنفسي"


def page_of(scan_id: int | str) -> str:
    return f"{FORM}/{scan_id}"


async def finished_scan(db, owner_user, **columns):
    """A done scan with a verified scene, two stages, two model calls and one insight."""
    started = clock.utcnow() - timedelta(seconds=30)
    values = {
        "status": ScanStatus.DONE,
        "outcome": ScanOutcome.INSIGHTS,
        "scene": scene(entity("e1", "plant"), entity("e2", "rain", box=None)).model_dump(
            mode="json"
        ),
        "clarification_question": "أيّ نبتة تقصد؟",
        "clarification_answer": TYPED_ANSWER,
        "focus": {"box": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2}, "label": TYPED_LABEL},
        "created_at": started,
        "finished_at": started + timedelta(seconds=12),
        "awaiting_ruling": [{"collection": "muslim", "number": "898"}],
    }
    scan = scan_row(Owner(user_id=owner_user.id), **(values | columns))
    db.add(scan)
    await db.flush()
    insight = insight_row(Owner(user_id=owner_user.id), scan_id=scan.id)
    db.add(insight)
    await db.flush()
    db.add_all(
        [
            ScanEvent(
                at=started,
                scan_id=scan.id,
                run=1,
                stage="detect",
                status="skipped",
                ms=3,
                code="detector_off",
            ),
            ScanEvent(
                at=started + timedelta(seconds=5),
                scan_id=scan.id,
                run=1,
                stage="understand",
                status="done",
                ms=4800,
            ),
            ScanEvent(
                at=started + timedelta(seconds=12),
                scan_id=scan.id,
                run=1,
                stage="job",
                status="done",
                ms=12000,
                code="insights",
            ),
            AiCall(
                at=started,
                scan_id=scan.id,
                provider="openai",
                model="gpt-5.4-mini",
                stage="vision",
                kind="scene",
                attempts=1,
                input_tokens=1200,
                output_tokens=300,
                reasoning_tokens=0,
                cached_input_tokens=0,
                cost_usd=0.0021,
                latency_ms=4700,
                ok=True,
                retried_errors=[],
            ),
            AiCall(
                at=started + timedelta(seconds=6),
                scan_id=None,
                insight_id=insight.id,
                provider="openai",
                model="gpt-5.4-nano",
                stage="chat",
                kind="answer",
                attempts=2,
                input_tokens=400,
                output_tokens=0,
                reasoning_tokens=0,
                cached_input_tokens=0,
                cost_usd=None,
                latency_ms=900,
                ok=False,
                error_code="timeout",
                retried_errors=["network"],
            ),
        ]
    )
    await db.flush()
    return scan, insight


async def test_the_panel_shows_the_trace_and_nothing_of_the_person(admin, make_user, db_session):
    http, _ = admin
    owner = await make_user("owner@example.com")
    scan, insight = await finished_scan(db_session, owner)

    page = await http.get(page_of(scan.id))

    assert page.status_code == 200
    body = page.text
    assert f"Scan {scan.id}" in body
    assert 'id="scan-status">done<' in body
    assert 'id="scan-engine">pipeline<' in body
    assert "12000 ms" in body
    # The stages with their times and codes.
    for stage in ("detect", "understand", "job", "detector_off", "4800"):
        assert stage in body
    # The model calls: provider, model names, cost and the failure's code.
    for call in ("gpt-5.4-mini", "gpt-5.4-nano", "0.00210", "failed: timeout", "retried: network"):
        assert call in body
    assert "2 calls, 1 failed" in body
    assert "0.0021 USD" in body
    # The scene's entities and the insight by its references, never the cited text.
    for shown in ("e1", "plant", "e2", "rain", "نبتة صغيرة تحت المطر", "fake-vision"):
        assert shown in body
    assert f"<code>{insight.id}</code>" in body
    assert "30:50" in body
    assert "bukhari 1032" in body
    assert "T01_06" in body
    assert "muslim 898" in body
    assert "أيّ نبتة تقصد؟" in body
    # Nothing of the person: the typed answer, the drawn box's label, the owner.
    assert TYPED_ANSWER not in body
    assert TYPED_LABEL not in body
    assert str(owner.id) not in body
    assert "owner@example.com" not in body
    assert "<img" not in body


async def test_a_look_at_a_scan_is_audited_by_its_id(admin, make_user, db_session):
    http, me = admin
    owner = await make_user("owner@example.com")
    scan, _ = await finished_scan(db_session, owner)

    await http.get(page_of(scan.id))

    row = (await audit_rows(db_session))[-1]
    assert (row.action, row.admin_user_id, row.model, row.record_id) == (
        AuditAction.VIEW,
        me.id,
        "scan",
        str(scan.id),
    )


async def test_a_scan_with_nothing_stored_yet_still_has_a_page(admin, make_user, db_session):
    http, _ = admin
    owner = await make_user("owner@example.com")
    scan = scan_row(Owner(user_id=owner.id))
    db_session.add(scan)
    await db_session.flush()

    page = await http.get(page_of(scan.id))

    assert page.status_code == 200
    assert 'id="scan-status">queued<' in page.text
    assert "No scene was stored." in page.text
    assert "No stage was recorded" in page.text
    assert "No model call was recorded" in page.text
    assert "No insight." in page.text
    assert "0 calls" in page.text


async def test_an_insight_without_a_verse_or_a_hadith_shows_a_dash(admin, make_user, db_session):
    http, _ = admin
    owner = await make_user("owner@example.com")
    scan = scan_row(Owner(user_id=owner.id))
    db_session.add(scan)
    await db_session.flush()
    bare = insight_row(
        Owner(user_id=owner.id),
        scan_id=scan.id,
        quran_surah=None,
        quran_ayah=None,
        quran_evidence=None,
        hadith_collection=None,
        hadith_number=None,
        hadith_evidence=None,
        learning_unit_id=None,
    )
    db_session.add(bare)
    await db_session.flush()

    page = await http.get(page_of(scan.id))

    assert page.status_code == 200
    row = page.text.split(f"<code>{bare.id}</code>", 1)[1].split("</tr>", 1)[0]
    assert row.count("—") == 3


async def test_an_unknown_scan_has_no_page(admin, db_session):
    http, _ = admin

    missing = await http.get(page_of(999_999))

    assert missing.status_code == 404
    assert "No scan has this id." in missing.text
    assert (await audit_rows(db_session))[-1].record_id == "999999"
    # An id the database could not hold names nothing, and is not even looked up or audited.
    before = len(await audit_rows(db_session))
    assert (await http.get(page_of(10**23))).status_code == 404
    assert (await http.get(page_of(0))).status_code == 404
    assert len(await audit_rows(db_session)) == before


async def test_the_form_opens_a_scan_by_its_id_and_refuses_what_is_not_one(admin):
    http, _ = admin

    form = await http.get(FORM)
    sent = await http.get(FORM, params={"scan_id": " 42 "})
    refused = await http.get(FORM, params={"scan_id": "abc"})

    assert form.status_code == 200
    assert 'name="scan_id"' in form.text
    assert sent.status_code == 303
    assert sent.headers["location"].endswith(page_of(42))
    assert refused.status_code == 400
    assert "A scan id is a positive decimal number." in refused.text


async def test_the_panel_needs_an_admin_session(anon):
    for path in (FORM, page_of(42)):
        response = await anon.get(path)
        assert response.status_code in (302, 303), path
        assert "/admin/login" in response.headers["location"]


async def test_the_panel_is_gone_when_the_feature_is_off(make_admin_app, make_admin):
    await make_admin()
    app = make_admin_app(disabled_features="dev_inspector")
    async with browser(app) as http:
        assert (await sign_in(http)).status_code == 302
        assert (await http.get(FORM)).status_code == 404
        assert (await http.get(page_of(42))).status_code == 404
        assert "Scan inspector" not in (await http.get("/admin/")).text


@pytest.mark.parametrize("path", [FORM, page_of(42)])
async def test_the_sidebar_names_the_panel_when_it_is_on(admin, path):
    http, _ = admin
    page = await http.get(path)
    assert "Scan inspector" in page.text
