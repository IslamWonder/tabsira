"""The ontology views: the review of candidates, with the reviewer recorded, and the read-only entities."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.models import AuditAction, OntologyCandidate
from tests.support_admin import audit_rows, candidate, csrf_of, entity


async def post_action(http, name, pks):
    return await http.post(
        f"/admin/ontology-candidate/action/{name}?pks={pks}",
        data={"csrf_token": await csrf_of(http)},
    )


async def reload(db_session, row):
    await db_session.refresh(row)
    return row


# ─── Candidates ────────────────────────────────────────────────────


async def test_the_candidates_list_puts_the_most_proposed_first_and_shows_the_review(
    admin, db_session
):
    http, _ = admin
    db_session.add_all(
        [candidate("نادر", count=1), candidate("شائع", count=40), candidate("وسط", count=7)]
    )
    await db_session.flush()

    page = await http.get("/admin/ontology-candidate/list")

    assert page.status_code == 200
    body = page.text
    assert body.index("شائع") < body.index("وسط") < body.index("نادر")
    for header in ("Term", "Kind", "Count", "Status", "Reviewed at", "Reviewed by"):
        assert header in body


async def test_the_candidates_are_searched_by_term_and_filtered_by_status_and_kind(
    admin, db_session
):
    http, _ = admin
    db_session.add_all(
        [
            candidate("طائرة", status="new"),
            candidate("سيارة", status="accepted"),
            candidate("قطار", status="rejected", kind="concept"),
        ]
    )
    await db_session.flush()

    by_term = await http.get("/admin/ontology-candidate/list?search=طائرة")
    accepted = await http.get("/admin/ontology-candidate/list?status=accepted")
    concepts = await http.get("/admin/ontology-candidate/list?kind=concept")

    assert "طائرة" in by_term.text
    assert "سيارة" not in by_term.text
    assert "سيارة" in accepted.text
    assert "طائرة" not in accepted.text
    assert "قطار" in concepts.text
    assert "طائرة" not in concepts.text


async def test_a_candidates_page_shows_its_examples_and_who_reviewed_it(admin, db_session):
    http, me = admin
    row = candidate("طائرة", examples=["مشهد مطار"], status="accepted", reviewed_by=me.id)
    db_session.add(row)
    await db_session.flush()

    page = await http.get(f"/admin/ontology-candidate/details/{row.id}")

    assert page.status_code == 200
    assert "مشهد مطار" in page.text
    assert str(me.id) in page.text


async def test_accepting_records_the_decision_the_time_and_the_reviewer(
    admin, db_session, moving_clock
):
    http, me = admin
    one, two, other = candidate("أ"), candidate("ب"), candidate("ج")
    db_session.add_all([one, two, other])
    await db_session.flush()

    response = await post_action(http, "accept", f"{one.id},{two.id}")

    assert response.status_code == 303
    assert response.headers["location"].endswith("/admin/ontology-candidate/list")
    for row in (one, two):
        await reload(db_session, row)
        assert (row.status, row.reviewed_by, row.reviewed_at) == (
            "accepted",
            me.id,
            moving_clock.now,
        )
    await reload(db_session, other)
    assert (other.status, other.reviewed_by, other.reviewed_at) == ("new", None, None)
    row = [r for r in await audit_rows(db_session) if r.action is AuditAction.BULK_ACTION][-1]
    assert (row.model, row.admin_user_id) == ("ontology-candidate", me.id)
    assert row.details == {"reason": "accept", "count": 2, "ids": [str(one.id), str(two.id)]}


async def test_rejecting_records_a_rejection_and_a_later_decision_replaces_it(admin, db_session):
    http, me = admin
    row = candidate("أ")
    db_session.add(row)
    await db_session.flush()

    await post_action(http, "reject", row.id)
    await reload(db_session, row)
    assert (row.status, row.reviewed_by) == ("rejected", me.id)

    await post_action(http, "accept", row.id)
    await reload(db_session, row)
    assert row.status == "accepted"


async def test_an_action_with_nothing_usable_selected_changes_nothing(admin, db_session):
    http, _ = admin
    row = candidate("أ")
    db_session.add(row)
    await db_session.flush()

    for pks in ("", "abc", "-1,x"):
        response = await post_action(http, "accept", pks)
        assert response.status_code == 303
        assert "error=Select+at+least+one+candidate+first." in response.headers["location"]

    await reload(db_session, row)
    assert row.status == "new"


async def test_the_candidates_list_offers_accept_and_reject_with_confirmations(admin):
    http, _ = admin

    page = await http.get("/admin/ontology-candidate/list")

    for slug in ("accept", "reject"):
        assert f"action-customconfirm-{slug}" in page.text
    assert "Accept the selected candidates?" in page.text


async def test_an_action_is_not_a_get_and_needs_the_token(admin, db_session):
    http, _ = admin
    row = candidate("أ")
    db_session.add(row)
    await db_session.flush()

    assert (
        await http.get(f"/admin/ontology-candidate/action/accept?pks={row.id}")
    ).status_code == 405
    assert (
        await http.post(f"/admin/ontology-candidate/action/accept?pks={row.id}")
    ).status_code == 403
    await reload(db_session, row)
    assert row.status == "new"


async def test_the_only_thing_an_editor_types_is_a_note_and_it_counts_as_a_review(
    admin, db_session, moving_clock
):
    http, me = admin
    row = candidate("أ")
    db_session.add(row)
    await db_session.flush()

    page = await http.get(f"/admin/ontology-candidate/edit/{row.id}")
    assert 'name="review_note"' in page.text
    for absent in ("term", "status", "count", "entity_id", "reviewed_by"):
        assert f'name="{absent}"' not in page.text

    response = await http.post(
        f"/admin/ontology-candidate/edit/{row.id}",
        data={
            "review_note": "A drone, not a plane: add under aircraft.",
            "csrf_token": await csrf_of(http),
            "save": "Save",
        },
    )

    assert response.status_code == 302
    await reload(db_session, row)
    assert row.review_note == "A drone, not a plane: add under aircraft."
    assert (row.reviewed_by, row.reviewed_at, row.status) == (me.id, moving_clock.now, "new")
    update = [r for r in await audit_rows(db_session) if r.action is AuditAction.UPDATE][-1]
    assert update.details == {"fields": ["review_note"]}
    assert "A drone" not in repr(update.details)


async def test_candidates_cannot_be_created_or_deleted_or_exported(admin, db_session):
    http, _ = admin
    row = candidate("أ")
    db_session.add(row)
    await db_session.flush()
    token = await csrf_of(http)

    assert (await http.get("/admin/ontology-candidate/create")).status_code == 403
    assert (
        await http.delete(
            f"/admin/ontology-candidate/delete?pks={row.id}", headers={"X-CSRF-Token": token}
        )
    ).status_code == 403
    assert (await http.get("/admin/ontology-candidate/export/csv")).status_code == 403
    assert (await db_session.scalars(select(OntologyCandidate))).all() == [row]


# ─── Entities ──────────────────────────────────────────────────────


async def test_entities_are_listed_and_shown_but_never_changed(admin, db_session):
    http, _ = admin
    db_session.add_all(
        [entity("E001"), entity("E002", label_ar="جبل", label_norm="جبل", domain="التضاريس")]
    )
    await db_session.flush()

    listing = await http.get("/admin/ontology-entity/list")
    found = await http.get("/admin/ontology-entity/list?search=جبل")
    page = await http.get("/admin/ontology-entity/details/E001")

    assert "سماء" in listing.text
    assert "جبل" in listing.text
    assert "سماء" not in found.text.split("<tbody>")[-1]
    assert "جبل" in found.text
    for shown in ("أفق", "نظر", "خلق", "Related objects"):
        assert shown in page.text
    for hidden in ("search_text", "label_norm", "Raw", "related_norm"):
        assert hidden not in page.text
    assert (await http.get("/admin/ontology-entity/create")).status_code == 403
    assert (await http.get("/admin/ontology-entity/edit/E001")).status_code == 403


@pytest.mark.parametrize("path", ["ontology-candidate", "ontology-entity"])
async def test_a_signed_out_browser_reaches_neither_view(anon, path):
    assert (await anon.get(f"/admin/{path}/list")).status_code == 302
