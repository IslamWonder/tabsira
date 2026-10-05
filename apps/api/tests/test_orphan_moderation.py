"""
«كفالة بصيرة», moderation (decision 60): an orphaned entry is moderated.

A moderator can remove, hold and restore an orphaned entry without ever turning it back into one
that names its author, and an entry with sponsoring switched off is still served, anonymous and
plain.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from src import clock
from src.features import FeatureFlag
from src.models import (
    MapEntry,
    MapEntryStatus,
    Report,
    ReportReason,
    ReportTarget,
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
from tests.test_admin_moderation import QUEUE, decide, page_of
from tests.test_atlas import _insight, _place, _published

MODERATOR = __import__("uuid").uuid4()


@pytest.fixture
def admin_app(make_admin_app, account_settings):
    """The admin application, keyed like the members' one: the two run in this one test."""
    return make_admin_app(hash_secret=account_settings.hash_secret.get_secret_value())


# ─── An orphaned entry, moderated ───


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


async def test_reports_hold_an_orphaned_entry_and_a_refusal_removes_it(
    db_session, factory, make_member, make_settings, world
):
    author, reader = await make_member("author"), await make_member("reader")
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
