"""
Apply quranpedia's corrections to mushaf 2 (decision 16), once a day.

quranpedia corrects its texts every week and lists every corrected verse in
`GET /v1/changes?since=<date>`. The sync asks for everything changed since its
last successful run, keeps the rows of mushaf 2, refetches only those verses,
and applies every text that differs from the stored one through
`apply_correction`: new text, hash and version stored, the previous text kept
in history, an audit row written.

The feed lists at most 1,000 rows per request, sorted by date, and `since` is
a date. When it is truncated the next request starts at the date of its last
row. If a single day holds more rows than one request returns, or more verses
changed than are worth refetching one by one, the sync reads the newest
verified dump instead, which carries every correction made before it was built.

Only one sync runs at a time: it takes a transaction-level advisory lock and
steps aside when another process holds it. Nothing is stored unless the whole
run succeeds, and then the date it reached is recorded for the next one.
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import QuranVerse, ScriptureSyncState
from src.scripture.errors import ScriptureError
from src.scripture.quran import (
    SYNC_SOURCE,
    QuranImportReport,
    apply_correction,
    load_json_file,
    parse_mushaf,
    reconcile_verses,
    refresh_verse_spans,
)
from src.scripture.quranpedia import (
    API_URL,
    MUSHAF_FILE,
    MUSHAF_ID,
    ChangedAyah,
    QuranpediaClient,
    dump_url,
    fetch_dump_files,
)
from src.scripture.text import sha256_hex

log = logging.getLogger("tabsira.scripture.sync")

# Any fixed number shared by every process that runs the sync.
SYNC_LOCK_KEY = 7_424_016
# Beyond this many changed verses, one dump download is kinder than one request per verse.
MAX_REFETCH = 200


class SyncError(ScriptureError):
    """The sync cannot run, or the feed named a verse the store does not hold."""


@dataclass
class SyncReport:
    since: str
    until: str = ""
    changed_rows: int = 0
    corrected: int = 0
    unchanged: int = 0
    via_dump: str | None = None
    skipped: bool = False
    corrections: list[str] = field(default_factory=list)


def change_tag(changed_at: str) -> str:
    """Return the `source_version` of a text that came from the changes feed."""
    return f"change:{changed_at}"


async def collect_changes(
    client: QuranpediaClient, since: date
) -> tuple[list[ChangedAyah], str, bool]:
    """
    Read the feed from `since`, following truncated pages.

    Return the latest row of each changed verse of mushaf 2, the `until` of the
    first page, and whether the feed could be read to its end.
    """
    rows: dict[tuple[int, int], ChangedAyah] = {}
    first_until: str | None = None
    current = since
    while True:
        feed = await client.changes(current)
        first_until = first_until or feed.until
        for row in feed.ayahs.rows:
            if row.mushaf == MUSHAF_ID:
                rows[(row.surah, row.ayah)] = row
        if not feed.ayahs.truncated:
            return sorted(rows.values(), key=lambda r: (r.surah, r.ayah)), first_until, True
        last = date.fromisoformat(feed.ayahs.rows[-1].changed_at[:10])
        if last <= current:
            return sorted(rows.values(), key=lambda r: (r.surah, r.ayah)), first_until, False
        current = last


async def _apply_rows(
    session: AsyncSession, client: QuranpediaClient, rows: list[ChangedAyah], report: SyncReport
) -> None:
    """Refetch and apply every changed verse, then rebuild the verse spans once if any changed."""
    corrected = 0
    for row in rows:
        fetched = await client.ayah(row)
        verse = await session.scalar(
            select(QuranVerse).where(QuranVerse.surah == row.surah, QuranVerse.ayah == row.ayah)
        )
        if verse is None:
            message = f"the feed names verse {row.surah}:{row.ayah}, which the store does not hold"
            raise SyncError(message)
        # The verse's quranpedia id and page come with it; keep them as quranpedia has them now.
        verse.quranpedia_ayah_id = fetched.id
        verse.page = fetched.page_number
        if verse.text_sha256 == sha256_hex(fetched.text):
            report.unchanged += 1
            continue
        source = f"{API_URL}{row.refetch.removeprefix('/v1')} changed {row.changed_at}"
        await apply_correction(session, verse, fetched.text, change_tag(row.changed_at), source)
        corrected += 1
        report.corrections.append(f"{row.surah}:{row.ayah}")
    if corrected:
        await refresh_verse_spans(session)
    report.corrected += corrected


async def _apply_dump(
    session: AsyncSession, client: QuranpediaClient, cache_dir: Path, report: SyncReport
) -> str:
    files = await fetch_dump_files(client, cache_dir)
    dump = parse_mushaf(load_json_file(files.mushaf))
    if not dump.is_complete():
        message = f"the dump {files.version} is not a whole mushaf; refusing to sync from it"
        raise SyncError(message)
    imported = QuranImportReport(version=dump.version)
    source = f"{dump_url(MUSHAF_FILE)} version {files.version}"
    await reconcile_verses(session, dump, source, imported)
    report.via_dump = dump.version
    report.corrected = imported.corrected
    report.unchanged = imported.unchanged + imported.metadata_updated
    return dump.version


async def sync_quran(
    session: AsyncSession, client: QuranpediaClient, *, cache_dir: Path
) -> SyncReport:
    """Apply every correction made since the last successful sync; run with the sync guard open."""
    locked = await session.scalar(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": SYNC_LOCK_KEY}
    )
    state = await session.get(ScriptureSyncState, SYNC_SOURCE)
    if not locked:
        return SyncReport(since=state.synced_through.isoformat() if state else "", skipped=True)
    if state is None:
        message = "no sync state: import the Quran first (import_scripture quran)"
        raise SyncError(message)

    report = SyncReport(since=state.synced_through.isoformat())
    rows, until, complete = await collect_changes(client, state.synced_through)
    report.until = until
    report.changed_rows = len(rows)
    if complete and len(rows) <= MAX_REFETCH:
        await _apply_rows(session, client, rows, report)
    else:
        log.info("%d changed verses, feed complete: %s; reading the dump", len(rows), complete)
        state.dump_version = await _apply_dump(session, client, cache_dir, report)

    state.synced_through = datetime.fromisoformat(until).astimezone(UTC).date()
    state.last_success_at = datetime.now(UTC)
    state.last_summary = dataclasses.asdict(report)
    await session.flush()
    return report
