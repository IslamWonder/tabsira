"""
«كفالة بصيرة» (decision 60): a verified member looks after an orphaned atlas entry.

One sponsor at a time. Sponsoring returns the entry to `published` at the place it was widened
to (it is never narrowed again, `atlas_service.place`), with the author's name still hidden and
the sponsor's handle shown: the sponsor chose to be named. The sponsor may write one reflection,
their own words under the entry. It passes the same guard as a comment before anyone sees it,
and is refused outright when it reads like Quran or hadith, which only the store may supply.
Nothing scores, ranks or rewards a sponsor.

A sponsor who ends the sponsorship, or an author who withdraws the entry, deletes the row and the
reflection with it. The entry stays published
until the daily job orphans it again after `ORPHAN_AFTER_DAYS` without a sign of life.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock
from src.errors import AppError, ErrorCode
from src.models.atlas import MapEntry, MapEntrySponsorship, MapEntryStatus
from src.models.scan import Insight
from src.models.social import CommentStatus
from src.models.user import User
from src.schemas.atlas import SponsorshipOut
from src.services import atlas_service, moderation_service, publication_service
from src.services.moderation_guard import TextGuard
from src.services.post_service import looks_like_scripture
from src.services.post_view import outcome_message

OWN_ENTRY = "You cannot sponsor your own insight."
ALREADY_SPONSORED = "This insight already has a sponsor."
NOT_ORPHANED = "This insight is not waiting for a sponsor."
NO_REFLECTION_NOW = "The entry cannot take a reflection now."
CHANGED_MEANWHILE = "The reflection changed while it was reviewed."
LOOKS_LIKE_SCRIPTURE = "A reflection is your own words: it cannot quote the Quran or a hadith."
UNDER_13 = "You cannot sponsor an insight: the account declared it is under 13."


def _conflict(message: str) -> AppError:
    return AppError(ErrorCode.CONFLICT, message, status_code=409)


def _not_sponsoring() -> AppError:
    return AppError(ErrorCode.NOT_FOUND, "You do not sponsor this entry.", status_code=404)


async def _own_sponsorship(db: AsyncSession, entry_id: int, sponsor: User) -> MapEntrySponsorship:
    """Load the sponsor's own sponsorship of the entry, locked, or raise 404."""
    found = await db.scalar(
        select(MapEntrySponsorship)
        .where(MapEntrySponsorship.entry_id == entry_id, MapEntrySponsorship.user_id == sponsor.id)
        .with_for_update()
    )
    if found is None:
        raise _not_sponsoring()
    return found


async def start(db: AsyncSession, sponsor: User, entry_id: int) -> MapEntrySponsorship:
    """
    Open a sponsorship of an orphaned entry and put the entry back on the atlas.

    Refused: an account that declared it is under 13 (409 `UNDER_13_CANNOT_PUBLISH`); an entry
    the caller cannot see (404, as for one that does not exist; a block against the entry's
    author does not count, since the author is anonymous); the caller's own entry (409); an entry
    that is sponsored already, or that is not orphaned (409). The entry is locked, so two members
    cannot both succeed, and neither can a sponsorship and the author placing the entry again.
    """
    await publication_service.refuse_under_13(db, sponsor.id, UNDER_13)
    entry = await atlas_service.published_entry(db, entry_id, sponsor)
    await db.refresh(entry, with_for_update=True)
    if entry.user_id == sponsor.id:
        raise _conflict(OWN_ENTRY)
    if await atlas_service.is_sponsored(db, entry.id):
        raise _conflict(ALREADY_SPONSORED)
    if entry.status is not MapEntryStatus.ORPHANED:
        raise _conflict(NOT_ORPHANED)
    now = clock.utcnow()
    sponsorship = MapEntrySponsorship(entry_id=entry.id, user_id=sponsor.id, started_at=now)
    db.add(sponsorship)
    entry.status = MapEntryStatus.PUBLISHED
    entry.last_active_at = now
    await db.flush()
    return sponsorship


async def end(db: AsyncSession, sponsor: User, entry_id: int) -> None:
    """End the caller's sponsorship by deleting it, the reflection with it; the entry stays published."""
    sponsorship = await _own_sponsorship(db, entry_id, sponsor)
    await db.delete(sponsorship)
    await db.flush()


async def write_reflection(
    db: AsyncSession, sponsor: User, entry_id: int, text: str, guard: TextGuard
) -> MapEntrySponsorship:
    """
    Create or replace the sponsor's reflection and have the guard judge it.

    Text that reads like scripture is refused before anything is stored (422). The account must
    still be allowed to publish (not under 13) and still see the entry. The words wait in
    `pending_review`, seen by their sponsor alone, until the guard has decided: published, refused
    with a reason, or held for the moderation queue, and the decision goes to the moderation log
    as a comment's does. The guard is a network call, so the transaction is committed before it
    and the row is locked and read again after it; a sponsorship that ended, or words replaced,
    meanwhile end the call with a 409 rather than a verdict about other words. Writing is a sign
    of life for the entry, whatever the verdict.
    """
    if looks_like_scripture(text):
        raise AppError(ErrorCode.VALIDATION_ERROR, LOOKS_LIKE_SCRIPTURE, status_code=422)
    await publication_service.refuse_under_13(db, sponsor.id, UNDER_13)
    entry = await atlas_service.published_entry(db, entry_id, sponsor)
    sponsorship = await _own_sponsorship(db, entry.id, sponsor)
    if entry.status is not MapEntryStatus.PUBLISHED:
        raise _conflict(NO_REFLECTION_NOW)
    sponsorship.reflection = text
    sponsorship.reflection_status = CommentStatus.PENDING_REVIEW
    sponsorship.reflection_reason = None
    entry.last_active_at = clock.utcnow()
    sponsorship_id = sponsorship.id
    await db.commit()
    verdict = await guard.check(text)
    locked = (
        await db.execute(
            select(MapEntrySponsorship)
            .where(MapEntrySponsorship.id == sponsorship_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if locked is None or locked.reflection != text:
        raise _conflict(CHANGED_MEANWHILE)
    moderation_service.settle(db, locked, verdict)
    return locked


def _out(sponsorship: MapEntrySponsorship, entry: MapEntry, title: str) -> SponsorshipOut:
    status = sponsorship.reflection_status
    return SponsorshipOut(
        entry_id=entry.id,
        title=title,
        place=atlas_service.place_of(entry),
        widened_level=entry.widened_level,
        id=sponsorship.id,
        active=True,
        started_at=sponsorship.started_at,
        ended_at=None,
        reflection=sponsorship.reflection,
        reflection_status=status,
        reflection_message=(
            None if status is None else outcome_message(status.value, sponsorship.reflection_reason)
        ),
    )


async def list_mine(
    db: AsyncSession, sponsor: User, *, everything: bool = False
) -> list[SponsorshipOut]:
    """
    Return the caller's sponsorships, newest first, with their own reflection in any state.

    Only entries that are still on the atlas, unless `everything`: one a moderator holds shows
    nothing of itself in the app's list, but the sponsor's own reflection on it is their data and
    goes in their export.
    """
    statement = (
        select(MapEntrySponsorship, MapEntry, Insight.title)
        .join(MapEntry, MapEntry.id == MapEntrySponsorship.entry_id)
        .join(Insight, Insight.id == MapEntry.insight_id)
        .where(MapEntrySponsorship.user_id == sponsor.id)
        .order_by(MapEntrySponsorship.started_at.desc(), MapEntrySponsorship.id.desc())
    )
    if not everything:
        statement = statement.where(MapEntry.status == MapEntryStatus.PUBLISHED)
    rows = await db.execute(statement)
    return [_out(sponsorship, entry, title) for sponsorship, entry, title in rows]
