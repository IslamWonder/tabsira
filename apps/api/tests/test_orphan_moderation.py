"""
«كفالة بصيرة», moderation (decision 60): an orphaned entry and a sponsor reflection are moderated.

A moderator can remove, hold and restore an orphaned entry without ever turning it back into one
that names its author, a sponsor reflection is reported, held, decided and logged like a
comment, and an entry with sponsoring switched off is still served, anonymous and plain.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from src import clock
from src.features import FeatureFlag
from src.models import (
    CommentStatus,
    MapEntry,
    MapEntryStatus,
    ModerationAction,
    ModerationActionKind,
    ModerationSource,
    Report,
    ReportReason,
    ReportStatus,
    ReportTarget,
    WidenLevel,
)
from src.services import moderation_service, orphan_service
from src.storage.photos import build_photo_store
from tests.helpers import switched
from tests.support_orphans import (
    NEAR_TUNIS,
    OLD,
    WHOLE,
    current_id,
    entry_row,
    fresh,
    run_job,
)
from tests.support_social import ALLOW, REVIEW
from tests.test_admin_moderation import QUEUE, decide, page_of
from tests.test_atlas import _insight, _place, _published
from tests.test_sponsorship import openings, reflect, url

MODERATOR = __import__("uuid").uuid4()


@pytest.fixture
def admin_app(make_admin_app, account_settings):
    """The admin application, keyed like the members' one: the two run in this one test."""
    return make_admin_app(hash_secret=account_settings.hash_secret.get_secret_value())


async def sponsored(db, factory, make_settings, author, sponsor, *, text: str | None = None) -> str:
    """An orphaned entry of `author` that `sponsor` looks after (with a reflection if given)."""
    entry = await entry_row(db, author)
    await run_job(factory, db, make_settings)
    entry_id = await current_id(db, entry.insight_id)
    assert (await sponsor.http.put(url(entry_id))).status_code == 200
    if text is not None:
        assert (await reflect(sponsor, entry_id, text)).status_code == 200
    return entry_id


# ─── An orphaned entry, moderated ───


async def test_a_moderator_removes_an_orphaned_entry_with_its_sponsorship_and_restores_it_orphaned(
    db_session, factory, make_member, make_settings, world, guard
):
    author, sponsor = await make_member("author"), await make_member("sponsor")
    entry_id = await sponsored(db_session, factory, make_settings, author, sponsor, text="كلمة")
    entry = await fresh(db_session, int(entry_id))
    # Sponsored and published: removal takes the sponsorship and its words with it.
    await moderation_service.remove(db_session, entry, MODERATOR, "spam")
    assert (entry.status, await openings(db_session)) == (MapEntryStatus.REMOVED, [])

    await moderation_service.approve(db_session, entry, MODERATOR)

    # No sponsor is left, so it is the anonymous orphan again, at the same place and level.
    assert entry.status is MapEntryStatus.ORPHANED and entry.widened_level is WidenLevel.REGION
    assert (entry.public_lat, entry.public_lng) == (36.8, 10.2)


async def test_a_moderator_removes_an_entry_that_was_orphaned_and_a_refusal_drops_nothing_else(
    db_session, factory, make_member, make_settings, world
):
    author = await make_member("author")
    entry = await entry_row(db_session, author)
    await run_job(factory, db_session, make_settings)
    orphan = await fresh(db_session, entry)

    await moderation_service.remove(db_session, orphan, MODERATOR, "spam")

    assert orphan.status is MapEntryStatus.REMOVED
    await moderation_service.approve(db_session, orphan, MODERATOR)
    assert orphan.status is MapEntryStatus.ORPHANED


async def test_reports_hold_an_orphaned_entry_and_approving_a_sponsored_one_publishes_it(
    db_session, factory, make_member, make_settings, world
):
    author, sponsor = await make_member("author"), await make_member("sponsor")
    reader = await make_member("reader")
    entry_id = await sponsored(db_session, factory, make_settings, author, sponsor)
    entry = await fresh(db_session, int(entry_id))
    db_session.add(
        Report(
            reporter_id=reader.user.id,
            target_type=ReportTarget.MAP_ENTRY,
            target_id=entry.id,
            reason=ReportReason.WRONG_PLACE,
        )
    )
    await db_session.flush()

    assert await moderation_service.hold_if_reported(db_session, entry, 1)
    await db_session.flush()
    assert entry.status is MapEntryStatus.PENDING_REVIEW
    await moderation_service.approve(db_session, entry, MODERATOR)

    # The sponsorship stood through the hold: the entry is the sponsored, published one.
    assert entry.status is MapEntryStatus.PUBLISHED and len(await openings(db_session)) == 1

    orphan = await entry_row(db_session, author)
    await run_job(factory, db_session, make_settings)
    held = await fresh(db_session, orphan)
    db_session.add(
        Report(
            reporter_id=reader.user.id,
            target_type=ReportTarget.MAP_ENTRY,
            target_id=held.id,
            reason=ReportReason.WRONG_PLACE,
        )
    )
    await db_session.flush()
    assert await moderation_service.hold_if_reported(db_session, held, 1)
    await db_session.flush()
    await moderation_service.reject(db_session, held, MODERATOR, "spam")
    assert held.status is MapEntryStatus.REMOVED


async def test_the_queue_lists_a_reported_orphaned_entry(
    admin, db_session, factory, make_member, make_settings, world
):
    http, _ = admin
    author, reader = await make_member("author"), await make_member("reader")
    entry = await entry_row(db_session, author)
    await run_job(factory, db_session, make_settings)
    orphan = await fresh(db_session, entry)
    db_session.add(
        Report(
            reporter_id=reader.user.id,
            target_type=ReportTarget.MAP_ENTRY,
            target_id=orphan.id,
            reason=ReportReason.WRONG_PLACE,
        )
    )
    await db_session.flush()

    queue = await http.get(QUEUE)
    page = await http.get(page_of("map_entry", orphan.id))
    removed = await decide(http, "map_entry", orphan.id, "remove", "spam")

    assert f"map entry {orphan.id}" in queue.text
    assert "Remove" in page.text
    assert removed.status_code == 303
    assert (await fresh(db_session, orphan)).status is MapEntryStatus.REMOVED


# ─── A sponsor reflection, moderated ───


async def test_a_reflection_is_reported_held_decided_and_logged_like_a_comment(
    admin,
    db_session,
    factory,
    make_member,
    make_settings,
    world,
    guard,
    account_app,
    account_settings,
):
    http, _ = admin
    guard.verdict = ALLOW
    author, sponsor = await make_member("author"), await make_member("sponsor")
    reporters = [await make_member(f"reader{n}") for n in range(2)]
    entry_id = await sponsored(
        db_session, factory, make_settings, author, sponsor, text="كلمة طيبة"
    )
    [row] = await openings(db_session)
    report = {"target_type": "sponsorship", "target_id": str(row.id), "reason": "abuse"}
    account_app.state.settings = account_settings.model_copy(
        update={"social_report_hold_threshold": 2}
    )

    assert (await sponsor.http.post("/reports", json=report)).status_code == 400
    assert (await reporters[0].http.post("/reports", json=report)).status_code == 201
    page = (await reporters[1].http.get(f"/atlas/entries/{entry_id}")).json()
    assert (page["sponsor_reflection"], page["sponsor_reflection_id"]) == ("كلمة طيبة", str(row.id))
    assert (await reporters[1].http.post("/reports", json=report)).status_code == 201

    # Two different reporters held it: hidden from everyone but the sponsor, until a person decides.
    await db_session.refresh(row)
    assert (
        row.reflection_status is CommentStatus.PENDING_REVIEW
        and row.reflection_reason == "reported"
    )
    shown = (await reporters[1].http.get(f"/atlas/entries/{entry_id}")).json()
    assert shown["sponsor"]["handle"] == "sponsor" and shown["sponsor_reflection"] is None
    mine = (await sponsor.http.get("/me/sponsorships")).json()
    assert (mine[0]["reflection"], mine[0]["reflection_status"]) == ("كلمة طيبة", "pending_review")
    assert "sponsor reflection" in (await http.get(QUEUE)).text
    item = await http.get(page_of("sponsorship", row.id))
    assert item.status_code == 200 and "كلمة طيبة" in item.text

    assert (await decide(http, "sponsorship", row.id, "approve")).status_code == 303
    await db_session.refresh(row)
    assert row.reflection_status is CommentStatus.PUBLISHED
    assert (await decide(http, "sponsorship", row.id, "remove", "spam")).status_code == 303
    await db_session.refresh(row)
    assert (row.reflection_status, row.reflection_reason) == (CommentStatus.REMOVED, "spam")
    gone = (await reporters[1].http.get(f"/atlas/entries/{entry_id}")).json()
    assert gone["sponsor_reflection"] is None and gone["sponsor_reflection_id"] is None
    mine = (await sponsor.http.get("/me/sponsorships")).json()
    assert mine[0]["reflection_status"] == "removed" and mine[0]["reflection_message"]
    # The sponsor is not locked out: they may write another.
    assert (await reflect(sponsor, entry_id, "كلمة جديدة")).json()[
        "reflection_status"
    ] == "published"
    log = list(
        await db_session.scalars(
            select(ModerationAction)
            .where(
                ModerationAction.target_id == row.id, ModerationAction.target_type == "sponsorship"
            )
            .order_by(ModerationAction.id)
        )
    )
    assert [(entry.action, entry.source) for entry in log] == [
        (ModerationActionKind.PUBLISHED, ModerationSource.GUARD),
        (ModerationActionKind.HELD, ModerationSource.REPORTS),
        (ModerationActionKind.PUBLISHED, ModerationSource.MODERATOR),
        (ModerationActionKind.REMOVED, ModerationSource.MODERATOR),
        (ModerationActionKind.PUBLISHED, ModerationSource.GUARD),
    ]


async def test_a_reflection_the_guard_holds_waits_in_the_queue_with_the_guard_in_the_log(
    admin, db_session, factory, make_member, make_settings, world, guard
):
    http, _ = admin
    author, sponsor = await make_member("author"), await make_member("sponsor")
    guard.verdict = REVIEW
    entry_id = await sponsored(db_session, factory, make_settings, author, sponsor, text="كلمة")
    [row] = await openings(db_session)

    assert f"sponsor reflection {row.id}" in (await http.get(QUEUE)).text
    assert (await decide(http, "sponsorship", row.id, "reject", "spam")).status_code == 303

    await db_session.refresh(row)
    assert row.reflection_status is CommentStatus.REJECTED
    held = (
        await db_session.scalars(
            select(ModerationAction.source).where(
                ModerationAction.target_id == row.id,
                ModerationAction.action == ModerationActionKind.HELD,
            )
        )
    ).all()
    assert list(held) == [ModerationSource.GUARD]
    assert (await sponsor.http.get(f"/atlas/entries/{entry_id}")).json()[
        "sponsor_reflection"
    ] is None


async def test_only_a_published_reflection_on_a_visible_entry_can_be_reported(
    db_session, factory, make_member, make_settings, world, guard, account_app, account_settings
):
    guard.verdict = ALLOW
    author, sponsor = await make_member("author"), await make_member("sponsor")
    reader = await make_member("reader")
    entry_id = await sponsored(db_session, factory, make_settings, author, sponsor)
    [row] = await openings(db_session)
    body = {"target_type": "sponsorship", "target_id": str(row.id), "reason": "spam"}

    assert (await reader.http.post("/reports", json=body)).status_code == 404  # no reflection yet
    assert (await reflect(sponsor, entry_id)).status_code == 200
    assert (await reader.http.put(f"/blocks/{sponsor.handle}")).status_code == 204
    assert (await reader.http.post("/reports", json=body)).status_code == 404  # sponsor blocked
    assert (await reader.http.delete(f"/blocks/{sponsor.handle}")).status_code == 204
    account_app.state.settings = switched(account_settings, off=[FeatureFlag.ATLAS_SPONSORSHIP])
    assert (await reader.http.post("/reports", json=body)).status_code == 404  # switched off
    account_app.state.settings = account_settings
    assert (await reader.http.post("/reports", json=body)).status_code == 201
    assert (await reader.http.post("/reports", json=body)).status_code == 201  # the first, again
    count = await db_session.scalar(
        select(Report).where(Report.status == ReportStatus.OPEN).limit(1)
    )
    assert count is not None


# ─── Sponsoring switched off ───


async def test_with_sponsoring_off_an_orphaned_entry_is_served_as_a_plain_anonymous_one(
    db_session, factory, make_member, make_settings, world, account_app, account_settings
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    entry = await entry_row(db_session, author)
    await run_job(factory, db_session, make_settings)
    entry_id = await current_id(db_session, entry.insight_id)
    account_app.state.settings = switched(account_settings, off=[FeatureFlag.ATLAS_SPONSORSHIP])

    window = (await guest.http.get("/atlas/entries", params=WHOLE)).json()["features"]
    page = (await guest.http.get(f"/atlas/entries/{entry_id}")).json()
    place = (await guest.http.get("/atlas/places/2464464")).json()

    assert [f["id"] for f in window] == [entry_id]
    assert window[0]["properties"]["author"] is None
    assert (window[0]["properties"]["orphaned"], window[0]["properties"]["sponsor"]) == (
        False,
        None,
    )
    assert (page["author"], page["orphaned"], page["sponsor"]) == (None, False, None)
    assert [f["id"] for f in place["entries"]] == [entry_id]
    assert (await guest.http.get("/atlas/orphans", params=NEAR_TUNIS)).status_code == 404
    # Switched on again, the same entry is the orphan it is.
    account_app.state.settings = account_settings
    assert (await guest.http.get("/atlas/entries", params=WHOLE)).json()["features"] == []


async def test_sponsorships_that_exist_are_not_shown_while_sponsoring_is_off(
    db_session, factory, make_member, make_settings, world, guard, account_app, account_settings
):
    guard.verdict = ALLOW
    author, sponsor = await make_member("author"), await make_member("sponsor")
    entry_id = await sponsored(db_session, factory, make_settings, author, sponsor, text="كلمة")
    account_app.state.settings = switched(account_settings, off=[FeatureFlag.ATLAS_SPONSORSHIP])

    page = (await sponsor.http.get(f"/atlas/entries/{entry_id}")).json()
    window = (await sponsor.http.get("/atlas/entries", params=WHOLE)).json()["features"]
    place = (await sponsor.http.get("/atlas/places/2464464")).json()

    assert (page["sponsor"], page["sponsor_reflection"]) == (None, None)
    assert window[0]["properties"]["sponsor"] is None
    assert place["entries"][0]["properties"]["sponsor"] is None


# ─── The sponsor, checked again when they write ───


async def test_an_account_that_says_it_is_under_13_after_sponsoring_cannot_write(
    db_session, factory, make_member, make_settings, world, guard
):
    guard.verdict = ALLOW
    author, sponsor = await make_member("author"), await make_member("sponsor")
    entry_id = await sponsored(db_session, factory, make_settings, author, sponsor)
    assert (await sponsor.http.patch("/profile", json={"age_range": "under_13"})).status_code == 200

    response = await reflect(sponsor, entry_id)

    assert (response.status_code, response.json()["error"]) == (409, "UNDER_13_CANNOT_PUBLISH")
    assert guard.texts == []


# ─── Placing and widening do not race ───


async def test_placing_again_sees_a_widening_done_meanwhile(
    db_session, factory, make_member, make_settings, world
):
    author = await make_member("author")
    insight_id = await _insight(db_session, author)
    entry_id = await _published(author, insight_id)
    loaded = await db_session.get(MapEntry, int(entry_id))
    assert loaded is not None and loaded.widened_level is None
    loaded.last_active_at = clock.utcnow() - timedelta(days=OLD)
    await db_session.flush()
    # The job widens it in a session of its own; this session still holds the old, narrow row.
    await orphan_service.mark_orphans(factory, 30, build_photo_store(make_settings()))

    placed = await _place(author, insight_id, latitude=36.80, longitude=10.18)

    assert placed.status_code == 200
    assert placed.json()["public"]["point"]["coordinates"] == [10.2, 36.8]
    assert placed.json()["public"]["widened_level"] == "region"
