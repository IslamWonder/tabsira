"""
The moderation queue: held and reported posts, comments and map entries, decided one at a time.

Every decision goes through the moderation service (the moderation log and the reports
follow), the reason is a code the app defines and never the moderator's words, a decision
made on a stale screen is refused, and the audit log keeps the item's id and the decision's
name, never the text. A map entry is shown as the public atlas shows it: the exact point its
owner gave never reaches the moderator's pages.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from src import clock
from src.geo.privacy import approximate
from src.models import (
    AuditAction,
    Comment,
    CommentStatus,
    LocationMeaning,
    LocationSource,
    MapCapturePoint,
    MapEntry,
    MapEntryStatus,
    ModerationAction,
    ModerationActionKind,
    ModerationSource,
    Post,
    PostStatus,
    RemovalSource,
    Report,
    ReportReason,
    ReportStatus,
    ReportTarget,
    User,
)
from src.owner import Owner
from tests.scans.builders import insight_row, scan_row
from tests.support_admin import audit_rows, csrf_of
from tests.support_social import new_comment, new_post

QUEUE = "/admin/moderation-queue"
# Where an owner says the photo was taken, to the exact metre, and the cell it is published in.
EXACT = (36.806512, 10.181534)
CELL_M = 1000


def page_of(kind: str, item_id: int) -> str:
    return f"{QUEUE}/{kind}/{item_id}"


async def report(db, reporter, kind: str, item_id: int, **columns) -> Report:
    columns.setdefault("reason", ReportReason.SPAM)
    row = Report(
        reporter_id=reporter.id, target_type=ReportTarget(kind), target_id=item_id, **columns
    )
    db.add(row)
    await db.flush()
    return row


async def decide(http, kind, item_id, decision, reason=None):
    data = {"csrf_token": await csrf_of(http)}
    if reason is not None:
        data["reason"] = reason
    return await http.post(f"{page_of(kind, item_id)}/{decision}", data=data)


async def new_map_entry(db, owner: User, **columns: Any) -> MapEntry:
    """An entry of `owner` placing a fresh insight in Tunis, with its exact point kept beside it."""
    scan = scan_row(Owner(user_id=owner.id))
    db.add(scan)
    await db.flush()
    insight = insight_row(Owner(user_id=owner.id), scan_id=scan.id)
    db.add(insight)
    await db.flush()
    lat, lng = approximate(*EXACT, CELL_M)
    status = columns.pop("status", MapEntryStatus.DRAFT)
    if status is MapEntryStatus.PUBLISHED:
        columns.setdefault("published_at", clock.utcnow())
    values: dict[str, Any] = {
        "public_lat": lat,
        "public_lng": lng,
        "cell_m": CELL_M,
        "location_meaning": LocationMeaning.CAPTURE_POINT,
        "place_geoname_id": 2464470,
        "place_label": "تونس",
        "admin_label": "ولاية تونس",
        "country_iso2": "TN",
        "country_label": "تونس",
    }
    entry = MapEntry(user_id=owner.id, insight_id=insight.id, status=status, **(values | columns))
    db.add(entry)
    await db.flush()
    db.add(
        MapCapturePoint(
            entry_id=entry.id,
            latitude=EXACT[0],
            longitude=EXACT[1],
            accuracy_m=12,
            source=LocationSource.DEVICE_CAPTURE,
        )
    )
    await db.flush()
    return entry


def assert_no_exact_point(body: str) -> None:
    """The moderator's pages carry the public cell, never the owner's coordinates."""
    assert str(EXACT[0]) not in body
    assert str(EXACT[1]) not in body
    assert "latitude" not in body
    assert "accuracy" not in body


async def log_rows(db, kind: str, item_id: int) -> list[ModerationAction]:
    return list(
        (
            await db.scalars(
                select(ModerationAction)
                .where(ModerationAction.target_type == kind, ModerationAction.target_id == item_id)
                .order_by(ModerationAction.id)
            )
        ).all()
    )


@pytest.fixture
async def authors(make_user):
    return await make_user("author@example.com"), await make_user("reader@example.com")


# ─── The queue ─────────────────────────────────────────────────────


async def test_the_queue_lists_held_items_and_reported_published_ones_oldest_first(
    admin, db_session, authors
):
    http, me = admin
    author, reader = authors
    held = await new_post(
        db_session, author, status=PostStatus.PENDING_REVIEW, status_reason="guard_uncertain"
    )
    reported = await new_post(db_session, author, status=PostStatus.PUBLISHED, reflection="ر")
    quiet = await new_post(db_session, author, status=PostStatus.PUBLISHED)
    draft = await new_post(db_session, author)
    await report(db_session, reader, "post", reported.id)
    await report(db_session, reader, "post", quiet.id, status=ReportStatus.DISMISSED)
    held_comment = await new_comment(
        db_session, quiet, author, status=CommentStatus.PENDING_REVIEW, body="ت"
    )
    fine_comment = await new_comment(db_session, quiet, author)

    page = await http.get(QUEUE)

    assert page.status_code == 200
    body = page.text
    assert "2 posts" in body
    assert "1 comment" in body
    assert body.index(f"post {held.id}") < body.index(f"post {reported.id}")
    assert f"post {quiet.id}" not in body
    assert f"post {draft.id}" not in body
    assert f"comment {held_comment.id}" in body
    assert f"comment {fine_comment.id}" not in body
    assert "guard_uncertain" in body
    assert "ر" not in body.split("<tbody>")[1]
    row = [r for r in await audit_rows(db_session) if r.action is AuditAction.LIST][-1]
    assert (row.model, row.admin_user_id) == ("moderation-queue", me.id)


async def test_an_empty_queue_says_so(admin):
    http, _ = admin

    page = await http.get(QUEUE)

    assert "No post is waiting." in page.text
    assert "No comment is waiting." in page.text
    assert "No map entry is waiting." in page.text


# ─── An item's page ────────────────────────────────────────────────


async def test_a_posts_page_shows_its_text_its_insight_its_reports_its_log_and_the_fitting_decisions(
    admin, db_session, authors
):
    http, me = admin
    author, reader = authors
    post = await new_post(
        db_session,
        author,
        status=PostStatus.PENDING_REVIEW,
        status_reason="guard_uncertain",
        reflection="كلام الكاتب",
    )
    await report(db_session, reader, "post", post.id, details="تفاصيل المبلّغ")
    db_session.add(
        ModerationAction(
            target_type="post",
            target_id=post.id,
            action=ModerationActionKind.HELD,
            source=ModerationSource.GUARD,
            reason="guard_uncertain",
        )
    )
    await db_session.flush()

    page = await http.get(page_of("post", post.id))

    assert page.status_code == 200
    body = page.text
    assert 'id="item-text" dir="rtl" lang="ar">كلام الكاتب</p>' in body
    assert "Published insight" in body
    assert "تفاصيل المبلّغ" in body
    assert "pending_review (guard_uncertain)" in body
    assert "held" in body and "guard" in body
    assert 'id="approve"' in body
    assert 'id="reject"' in body
    assert 'id="remove"' not in body
    assert 'name="reason"' in body
    assert "spam · " in body
    row = [r for r in await audit_rows(db_session) if r.action is AuditAction.VIEW][-1]
    assert (row.model, row.record_id, row.admin_user_id) == (
        "moderation-queue",
        f"post:{post.id}",
        me.id,
    )


async def test_a_published_item_offers_removal_and_a_removed_one_only_approval(
    admin, db_session, authors
):
    http, _ = admin
    author, _ = authors
    published = await new_post(db_session, author, status=PostStatus.PUBLISHED)
    comment = await new_comment(db_session, published, author, status=CommentStatus.REMOVED)

    post_page = await http.get(page_of("post", published.id))
    comment_page = await http.get(page_of("comment", comment.id))

    assert 'id="remove"' in post_page.text
    assert 'id="approve"' not in post_page.text
    assert 'id="reject"' not in post_page.text
    assert 'id="approve"' in comment_page.text
    assert "Publish it again." in comment_page.text
    assert 'id="remove"' not in comment_page.text
    assert "No text of the author" not in comment_page.text


async def test_a_draft_is_private_writing_and_has_no_page_even_after_a_review(
    admin, db_session, authors
):
    http, _ = admin
    author, _ = authors
    draft = await new_post(db_session, author, reflection="مسودة خاصة")
    db_session.add(
        ModerationAction(
            target_type="post",
            target_id=draft.id,
            action=ModerationActionKind.REJECTED,
            source=ModerationSource.GUARD,
            reason="spam",
        )
    )
    await db_session.flush()

    page = await http.get(page_of("post", draft.id))

    assert page.status_code == 404
    assert "مسودة خاصة" not in page.text
    assert (await decide(http, "post", draft.id, "approve")).status_code == 404
    await db_session.refresh(draft)
    assert draft.status is PostStatus.DRAFT


async def test_a_withdrawn_post_offers_no_decision(admin, db_session, authors):
    http, _ = admin
    author, _ = authors
    withdrawn = await new_post(
        db_session, author, status=PostStatus.REMOVED, removal_source=RemovalSource.OWNER
    )

    page = await http.get(page_of("post", withdrawn.id))

    assert page.status_code == 200
    assert "Nothing applies to this item as it is now." in page.text
    for button in ("approve", "reject", "remove"):
        assert f'id="{button}"' not in page.text


async def test_the_authors_and_the_reporters_words_are_escaped(admin, db_session, authors):
    http, _ = admin
    author, reader = authors
    post = await new_post(
        db_session, author, status=PostStatus.PENDING_REVIEW, reflection="<script>x</script>"
    )
    await report(db_session, reader, "post", post.id, details='"><img src=x onerror=y>')

    page = await http.get(page_of("post", post.id))

    assert "<script>x</script>" not in page.text
    assert "&lt;script&gt;x&lt;/script&gt;" in page.text
    assert "<img src=x" not in page.text


async def test_an_unknown_item_or_kind_has_no_page(admin, db_session):
    http, _ = admin

    assert (await http.get(page_of("post", 999_999))).status_code == 404
    assert (await http.get(page_of("map_entry", 999_999))).status_code == 404
    assert (await http.get(page_of("photo", 1))).status_code == 404
    assert (await decide(http, "post", 999_999, "approve")).status_code == 404
    assert (await decide(http, "photo", 1, "approve")).status_code == 404
    # An id the database could not hold, or a kind that is not one: not looked up, not audited.
    huge = 10**23
    assert (await http.get(page_of("post", huge))).status_code == 404
    assert (await decide(http, "post", huge, "approve")).status_code == 404
    assert (await http.get(page_of("post", 0))).status_code == 404
    assert (await http.get(page_of("free text typed by admin", 1))).status_code == 404
    viewed = [r for r in await audit_rows(db_session) if r.action is AuditAction.VIEW]
    assert [r.record_id for r in viewed] == ["post:999999", "map_entry:999999"]


async def test_the_decided_banner_names_only_a_record_this_view_wrote(admin):
    http, _ = admin

    for crafted in (
        "Session expired, sign in at evil.example",
        "post:",
        "photo:1",
        "post:1x",
        "map entry:1",
    ):
        page = await http.get(f"{QUEUE}?decided={crafted}")
        assert page.status_code == 200, crafted
        assert "Decided:" not in page.text, crafted


# ─── Decisions ─────────────────────────────────────────────────────


async def test_approving_a_held_post_publishes_it_closes_its_reports_and_logs_it(
    admin, db_session, authors, moving_clock
):
    http, me = admin
    author, reader = authors
    post = await new_post(db_session, author, status=PostStatus.PENDING_REVIEW)
    filed = await report(db_session, reader, "post", post.id)

    response = await decide(http, "post", post.id, "approve")

    assert response.status_code == 303
    assert response.headers["location"].endswith(f"{QUEUE}?decided=post%3A{post.id}")
    await db_session.refresh(post)
    assert (post.status, post.reviewed_by, post.published_at) == (
        PostStatus.PUBLISHED,
        me.id,
        moving_clock.now,
    )
    await db_session.refresh(filed)
    assert (filed.status, filed.handled_by) == (ReportStatus.DISMISSED, me.id)
    rows = await log_rows(db_session, "post", post.id)
    assert [(r.action, r.source, r.actor_id) for r in rows] == [
        (ModerationActionKind.PUBLISHED, ModerationSource.MODERATOR, me.id)
    ]
    audit = [r for r in await audit_rows(db_session) if r.action is AuditAction.UPDATE][-1]
    assert (audit.model, audit.record_id, audit.admin_user_id) == (
        "moderation-queue",
        f"post:{post.id}",
        me.id,
    )
    assert audit.details == {"reason": "approve"}
    queue = await http.get(response.headers["location"])
    assert f"Decided: post:{post.id}." in queue.text
    assert f"post {post.id}" not in queue.text.split("<tbody>")[-1]


async def test_rejecting_a_held_comment_records_the_reason_code_the_author_is_shown(
    admin, db_session, authors
):
    http, me = admin
    author, reader = authors
    post = await new_post(db_session, author, status=PostStatus.PUBLISHED)
    comment = await new_comment(db_session, post, author, status=CommentStatus.PENDING_REVIEW)
    filed = await report(db_session, reader, "comment", comment.id)

    response = await decide(http, "comment", comment.id, "reject", reason="spam")

    assert response.status_code == 303
    await db_session.refresh(comment)
    assert (comment.status, comment.status_reason, comment.reviewed_by) == (
        CommentStatus.REJECTED,
        "spam",
        me.id,
    )
    await db_session.refresh(filed)
    assert filed.status is ReportStatus.ACTIONED
    rows = await log_rows(db_session, "comment", comment.id)
    assert [(r.action, r.reason) for r in rows] == [(ModerationActionKind.REJECTED, "spam")]
    audit = [r for r in await audit_rows(db_session) if r.action is AuditAction.UPDATE][-1]
    assert (audit.record_id, audit.details) == (f"comment:{comment.id}", {"reason": "reject"})


async def test_removing_a_reported_post_takes_it_down_as_a_moderator(
    admin, db_session, authors, moving_clock
):
    http, me = admin
    author, reader = authors
    post = await new_post(db_session, author, status=PostStatus.PUBLISHED)
    await report(db_session, reader, "post", post.id, reason=ReportReason.ABUSE)

    response = await decide(http, "post", post.id, "remove", reason="harassment")

    assert response.status_code == 303
    await db_session.refresh(post)
    assert (post.status, post.status_reason, post.removal_source, post.removed_at) == (
        PostStatus.REMOVED,
        "harassment",
        RemovalSource.MODERATOR,
        moving_clock.now,
    )
    rows = await log_rows(db_session, "post", post.id)
    assert [(r.action, r.reason, r.actor_id) for r in rows] == [
        (ModerationActionKind.REMOVED, "harassment", me.id)
    ]


async def test_a_moderators_own_words_are_never_a_reason(admin, db_session, authors):
    http, _ = admin
    author, _ = authors
    post = await new_post(db_session, author, status=PostStatus.PENDING_REVIEW)

    # The guard's codes say why an item was held; a moderator cannot give them as a verdict.
    for reason in (None, "", "you are rude", "SPAM", "guard_unavailable", "reported"):
        response = await decide(http, "post", post.id, "reject", reason=reason)
        assert response.status_code == 400, reason
        assert "Choose a reason from the list" in response.text

    await db_session.refresh(post)
    assert post.status is PostStatus.PENDING_REVIEW
    assert await log_rows(db_session, "post", post.id) == []
    refused = [r for r in await audit_rows(db_session) if r.action is AuditAction.UPDATE]
    assert len(refused) == 6
    assert {(r.record_id, repr(r.details)) for r in refused} == {
        (f"post:{post.id}", "{'reason': 'refused'}")
    }
    assert "rude" not in "".join(repr(r.details) for r in refused)


async def test_a_decision_that_no_longer_fits_the_item_is_refused_and_the_page_reloaded(
    admin, db_session, authors
):
    http, _ = admin
    author, _ = authors
    post = await new_post(db_session, author, status=PostStatus.PENDING_REVIEW)
    withdrawn = await new_post(
        db_session,
        author,
        status=PostStatus.REMOVED,
        removal_source=RemovalSource.OWNER,
    )

    stale = await decide(http, "post", post.id, "remove", reason="spam")
    revived = await decide(http, "post", withdrawn.id, "approve")

    assert stale.status_code == 409
    assert "it was reloaded" in stale.text
    assert "pending_review" in stale.text
    assert revived.status_code == 409
    await db_session.refresh(post)
    await db_session.refresh(withdrawn)
    assert post.status is PostStatus.PENDING_REVIEW
    assert withdrawn.status is PostStatus.REMOVED
    assert await log_rows(db_session, "post", post.id) == []
    refused = [r for r in await audit_rows(db_session) if r.action is AuditAction.UPDATE]
    assert [(r.record_id, r.details) for r in refused] == [
        (f"post:{post.id}", {"reason": "refused"}),
        (f"post:{withdrawn.id}", {"reason": "refused"}),
    ]


async def test_an_unknown_decision_is_not_a_page(admin, db_session, authors):
    http, _ = admin
    author, _ = authors
    post = await new_post(db_session, author, status=PostStatus.PENDING_REVIEW)

    assert (await decide(http, "post", post.id, "feature")).status_code == 404
    await db_session.refresh(post)
    assert post.status is PostStatus.PENDING_REVIEW


async def test_a_decision_is_a_post_with_the_token(admin, db_session, authors):
    http, _ = admin
    author, _ = authors
    post = await new_post(db_session, author, status=PostStatus.PENDING_REVIEW)

    assert (await http.get(f"{page_of('post', post.id)}/approve")).status_code == 405
    assert (await http.post(f"{page_of('post', post.id)}/approve")).status_code == 403
    await db_session.refresh(post)
    assert post.status is PostStatus.PENDING_REVIEW


# ─── Map entries ───────────────────────────────────────────────────


async def test_the_queue_lists_held_and_reported_map_entries_by_their_place_never_a_point(
    admin, db_session, authors
):
    http, _ = admin
    owner, reader = authors
    held = await new_map_entry(
        db_session, owner, status=MapEntryStatus.PENDING_REVIEW, status_reason="reported"
    )
    reported = await new_map_entry(db_session, owner, status=MapEntryStatus.PUBLISHED)
    quiet = await new_map_entry(db_session, owner, status=MapEntryStatus.PUBLISHED)
    draft = await new_map_entry(db_session, owner)
    await report(db_session, reader, "map_entry", reported.id, reason=ReportReason.WRONG_PLACE)

    page = await http.get(QUEUE)

    assert page.status_code == 200
    body = page.text
    assert "2 map entries" in body
    assert body.index(f"map entry {held.id}") < body.index(f"map entry {reported.id}")
    assert f"map entry {quiet.id}" not in body
    assert f"map entry {draft.id}" not in body
    assert f"<code>{owner.id}</code>" in body
    assert "reported" in body
    assert_no_exact_point(body)


async def test_a_map_entrys_page_shows_the_public_place_its_insight_and_the_fitting_decisions(
    admin, db_session, authors
):
    http, me = admin
    owner, reader = authors
    entry = await new_map_entry(
        db_session, owner, status=MapEntryStatus.PENDING_REVIEW, status_reason="reported"
    )
    await report(db_session, reader, "map_entry", entry.id, reason=ReportReason.PRIVATE_INFORMATION)

    page = await http.get(page_of("map_entry", entry.id))

    assert page.status_code == 200
    body = page.text
    assert f"Map entry {entry.id}" in body
    assert 'id="item-location"' in body
    assert "تونس، ولاية تونس، تونس" in body
    assert f"نحو {CELL_M} م" in body
    assert "موضع الالتقاط، تقريبًا" in body
    lat, lng = approximate(*EXACT, CELL_M)
    assert f"{lat:.4f}, {lng:.4f}" in body
    assert "Placed insight" in body
    assert "الحياة في قطرة" in body
    assert "No text of the author" not in body
    assert "private_information" in body
    assert 'id="approve"' in body
    assert 'id="reject"' in body
    assert "Take the held entry down" in body
    assert 'id="remove"' not in body
    assert_no_exact_point(body)
    row = [r for r in await audit_rows(db_session) if r.action is AuditAction.VIEW][-1]
    assert (row.model, row.record_id, row.admin_user_id) == (
        "moderation-queue",
        f"map_entry:{entry.id}",
        me.id,
    )


async def test_a_map_entry_with_its_point_cleared_says_so(admin, db_session, authors):
    http, _ = admin
    owner, _ = authors
    entry = await new_map_entry(
        db_session,
        owner,
        status=MapEntryStatus.REMOVED,
        public_lat=None,
        public_lng=None,
        place_label=None,
        admin_label=None,
        country_label=None,
    )

    page = await http.get(page_of("map_entry", entry.id))

    assert page.status_code == 200
    assert "cleared" in page.text
    assert 'lang="ar">—</dd>' in page.text
    assert 'id="approve"' in page.text
    assert_no_exact_point(page.text)


async def test_a_draft_map_entry_is_the_owners_private_place_and_has_no_page(
    admin, db_session, authors
):
    http, _ = admin
    owner, _ = authors
    draft = await new_map_entry(db_session, owner)

    assert (await http.get(page_of("map_entry", draft.id))).status_code == 404
    assert (await decide(http, "map_entry", draft.id, "approve")).status_code == 404
    await db_session.refresh(draft)
    assert draft.status is MapEntryStatus.DRAFT


async def test_a_withdrawn_map_entry_offers_no_decision_and_takes_none(admin, db_session, authors):
    http, _ = admin
    owner, _ = authors
    withdrawn = await new_map_entry(
        db_session,
        owner,
        status=MapEntryStatus.WITHDRAWN,
        public_lat=None,
        public_lng=None,
        withdrawn_at=clock.utcnow(),
    )

    page = await http.get(page_of("map_entry", withdrawn.id))
    revived = await decide(http, "map_entry", withdrawn.id, "approve")

    assert page.status_code == 200
    assert "Nothing applies to this item as it is now." in page.text
    for button in ("approve", "reject", "remove"):
        assert f'id="{button}"' not in page.text
    assert revived.status_code == 409
    await db_session.refresh(withdrawn)
    assert withdrawn.status is MapEntryStatus.WITHDRAWN
    assert await log_rows(db_session, "map_entry", withdrawn.id) == []


async def test_approving_a_held_map_entry_publishes_it_closes_its_reports_and_logs_it(
    admin, db_session, authors, moving_clock
):
    http, me = admin
    owner, reader = authors
    entry = await new_map_entry(
        db_session, owner, status=MapEntryStatus.PENDING_REVIEW, status_reason="reported"
    )
    filed = await report(db_session, reader, "map_entry", entry.id)

    response = await decide(http, "map_entry", entry.id, "approve")

    assert response.status_code == 303
    assert response.headers["location"].endswith(f"{QUEUE}?decided=map_entry%3A{entry.id}")
    await db_session.refresh(entry)
    assert (entry.status, entry.status_reason, entry.reviewed_by, entry.published_at) == (
        MapEntryStatus.PUBLISHED,
        None,
        me.id,
        moving_clock.now,
    )
    await db_session.refresh(filed)
    assert (filed.status, filed.handled_by) == (ReportStatus.DISMISSED, me.id)
    rows = await log_rows(db_session, "map_entry", entry.id)
    assert [(r.action, r.source, r.actor_id) for r in rows] == [
        (ModerationActionKind.PUBLISHED, ModerationSource.MODERATOR, me.id)
    ]
    audit = [r for r in await audit_rows(db_session) if r.action is AuditAction.UPDATE][-1]
    assert (audit.model, audit.record_id, audit.details) == (
        "moderation-queue",
        f"map_entry:{entry.id}",
        {"reason": "approve"},
    )
    queue = await http.get(response.headers["location"])
    assert f"Decided: map_entry:{entry.id}." in queue.text
    assert f"map entry {entry.id}" not in queue.text.split("<tbody>")[-1]


async def test_removing_a_reported_map_entry_takes_it_off_the_map_with_a_reason_code(
    admin, db_session, authors, moving_clock
):
    http, me = admin
    owner, reader = authors
    entry = await new_map_entry(db_session, owner, status=MapEntryStatus.PUBLISHED)
    filed = await report(db_session, reader, "map_entry", entry.id, reason=ReportReason.WRONG_PLACE)

    page = await http.get(page_of("map_entry", entry.id))
    response = await decide(http, "map_entry", entry.id, "remove", reason="wrong_place")

    assert 'id="remove"' in page.text
    assert 'id="approve"' not in page.text
    assert response.status_code == 303
    await db_session.refresh(entry)
    assert (entry.status, entry.status_reason, entry.reviewed_by, entry.removed_at) == (
        MapEntryStatus.REMOVED,
        "wrong_place",
        me.id,
        moving_clock.now,
    )
    # The public point stays with the removed row for an appeal; the exact point is untouched.
    assert (entry.public_lat, entry.public_lng) == approximate(*EXACT, CELL_M)
    capture = await db_session.get(MapCapturePoint, entry.id)
    assert (capture.latitude, capture.longitude) == EXACT
    await db_session.refresh(filed)
    assert filed.status is ReportStatus.ACTIONED
    rows = await log_rows(db_session, "map_entry", entry.id)
    assert [(r.action, r.reason, r.actor_id) for r in rows] == [
        (ModerationActionKind.REMOVED, "wrong_place", me.id)
    ]


async def test_rejecting_a_held_map_entry_removes_it_and_never_takes_the_moderators_words(
    admin, db_session, authors
):
    http, me = admin
    owner, _ = authors
    entry = await new_map_entry(db_session, owner, status=MapEntryStatus.PENDING_REVIEW)

    refused = await decide(http, "map_entry", entry.id, "reject", reason="this place is wrong")
    response = await decide(http, "map_entry", entry.id, "reject", reason="wrong_place")

    assert refused.status_code == 400
    assert_no_exact_point(refused.text)
    assert response.status_code == 303
    await db_session.refresh(entry)
    assert (entry.status, entry.status_reason, entry.reviewed_by) == (
        MapEntryStatus.REMOVED,
        "wrong_place",
        me.id,
    )
    rows = await log_rows(db_session, "map_entry", entry.id)
    assert [(r.action, r.reason) for r in rows] == [(ModerationActionKind.REJECTED, "wrong_place")]
    refusals = [r for r in await audit_rows(db_session) if r.details == {"reason": "refused"}]
    assert [r.record_id for r in refusals] == [f"map_entry:{entry.id}"]


# ─── The reports and the moderation log ────────────────────────────


async def test_reports_and_the_moderation_log_are_listed_but_never_changed(
    admin, db_session, authors
):
    http, _ = admin
    author, reader = authors
    post = await new_post(db_session, author, status=PostStatus.PUBLISHED)
    filed = await report(db_session, reader, "post", post.id, details="تفاصيل")
    await decide(http, "post", post.id, "remove", reason="spam")
    token = await csrf_of(http)

    reports = await http.get("/admin/report/list")
    one = await http.get(f"/admin/report/details/{filed.id}")
    log = await http.get("/admin/moderation-action/list")

    assert reports.status_code == 200
    assert str(post.id) in reports.text
    assert "تفاصيل" not in reports.text
    assert "تفاصيل" in one.text
    assert log.status_code == 200
    assert "removed" in log.text and "moderator" in log.text
    for path in ("report/create", f"report/edit/{filed.id}", "moderation-action/create"):
        assert (await http.get(f"/admin/{path}")).status_code == 403
    assert (
        await http.delete(f"/admin/report/delete?pks={filed.id}", headers={"X-CSRF-Token": token})
    ).status_code == 403
    assert (await http.get("/admin/report/export/csv")).status_code == 403
    assert (await db_session.scalars(select(Report))).all() == [filed]
    assert len((await db_session.scalars(select(Post))).all()) == 1
    assert (await db_session.scalars(select(Comment))).all() == []


@pytest.mark.parametrize(
    "path",
    [
        QUEUE,
        f"{QUEUE}/post/1",
        f"{QUEUE}/map_entry/1",
        "/admin/report/list",
        "/admin/moderation-action/list",
    ],
)
async def test_a_signed_out_browser_reaches_nothing(anon, path):
    assert (await anon.get(path)).status_code == 302
