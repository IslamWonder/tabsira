"""The correction sync: changed verses refetched and applied, history kept, one process at a time."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
from sqlalchemy import event, func, select, text

from src.cli import sync_quran as sync_command
from src.models import (
    QuranVerse,
    QuranVerseHistory,
    QuranVerseSearch,
    QuranVerseStandardGuard,
    ScriptureAudit,
    ScriptureSyncState,
)
from src.models.scripture import quran_verse_spans, quran_verse_standard_spans
from src.scripture import quran, quran_sync
from src.scripture.guard import WritePurpose, allow_scripture_writes
from src.scripture.guard_fold import guard_fold
from src.scripture.quran_sync import SyncError, collect_changes, sync_quran
from src.scripture.standard_spelling import standard_skeleton
from src.scripture.text import sha256_hex
from tests.scripture.fake_http import FakeQuranpedia, dump_routes, json_response
from tests.scripture.fixtures import fixture_path, load_json, store_quran, verse_text

EARLIER_30_50 = load_json("kfgqpc-v13-30-50.json")["text"]
EARLIER_2_49 = load_json("kfgqpc-v13-2-49.json")["text"]
UNTIL = "2026-10-05T03:00:00+00:00"


def _row(surah: int, ayah: int, changed_at: str = "2026-10-04 16:51:13", mushaf: int = 2) -> dict:
    return {
        "mushaf": mushaf,
        "surah": str(surah),
        "ayah": ayah,
        "changed_at": changed_at,
        "refetch": f"/v1/mushafs/{mushaf}/{surah}/{ayah}",
    }


def _feed(
    rows: list[dict], *, truncated: bool = False, since: str = "2026-10-03"
) -> httpx.Response:
    base = load_json("quranpedia-changes.json")
    ayahs = {"count": len(rows), "truncated": truncated, "rows": rows}
    return json_response(
        {**base, "since": since, "until": UNTIL, "changes": {**base["changes"], "ayahs": ayahs}}
    )


def _verse_answer(surah: int, ayah: int) -> httpx.Response:
    """The real refetch of 30:50, or another fixture verse under a made-up id and page."""
    if (surah, ayah) == (30, 50):
        return httpx.Response(
            200, content=fixture_path("quranpedia-ayah-2-30-50.json").read_bytes()
        )
    return json_response(
        {
            "id": 1,
            "number": ayah,
            "surah": str(surah),
            "page_number": 1,
            "text": verse_text(surah, ayah),
        }
    )


async def _store(session, *, stale_30_50: bool = True, stale_2_49: bool = False) -> None:
    earlier = {}
    if stale_30_50:
        earlier[30, 50] = EARLIER_30_50
    if stale_2_49:
        earlier[2, 49] = EARLIER_2_49
    await store_quran(session, earlier=earlier)
    await allow_scripture_writes(session, WritePurpose.SYNC)


async def _verse_30_50(session) -> QuranVerse:
    return (
        await session.scalars(
            select(QuranVerse).where(QuranVerse.surah == 30, QuranVerse.ayah == 50)
        )
    ).one()


async def test_a_corrected_verse_is_refetched_stored_and_audited(db_session, tmp_path):
    await _store(db_session)
    fake = FakeQuranpedia(
        {
            "/v1/changes?since=2026-10-03": _feed(
                [_row(16, 124, mushaf=4), _row(30, 50), _row(1, 1, mushaf=6)]
            ),
            "/v1/mushafs/2/30/50": _verse_answer(30, 50),
        }
    )

    report = await sync_quran(db_session, fake.client(), cache_dir=tmp_path)

    verse = await _verse_30_50(db_session)
    history = (await db_session.scalars(select(QuranVerseHistory))).one()
    audit = (
        await db_session.scalars(select(ScriptureAudit).where(ScriptureAudit.action == "correct"))
    ).one()
    state = await db_session.get(ScriptureSyncState, quran.SYNC_SOURCE)
    assert (report.changed_rows, report.corrected, report.corrections) == (1, 1, ["30:50"])
    assert verse.text == load_json("quranpedia-ayah-2-30-50.json")["text"] == verse_text(30, 50)
    assert verse.text_sha256 == sha256_hex(verse.text)
    assert verse.source_version == "change:2026-10-04 16:51:13"
    assert (history.text, history.replaced_by_version) == (EARLIER_30_50, verse.source_version)
    assert (audit.old_sha256, audit.new_sha256) == (sha256_hex(EARLIER_30_50), verse.text_sha256)
    assert (
        audit.source == "https://api.quranpedia.net/v1/mushafs/2/30/50 changed 2026-10-04 16:51:13"
    )
    assert state is not None
    assert state.synced_through == date(2026, 10, 5)
    assert state.last_success_at is not None
    assert state.last_summary is not None
    assert state.last_summary["corrected"] == 1
    # Only mushaf 2 is refetched; the other mushafs' rows cost no request.
    assert [r.url.path for r in fake.requests] == ["/v1/changes", "/v1/mushafs/2/30/50"]


async def test_running_again_finds_the_text_already_right(db_session, tmp_path):
    await _store(db_session, stale_30_50=False)
    routes = {
        "/v1/changes": _feed([_row(30, 50)]),
        "/v1/mushafs/2/30/50": _verse_answer(30, 50),
    }

    report = await sync_quran(db_session, FakeQuranpedia(routes).client(), cache_dir=tmp_path)

    assert (report.corrected, report.unchanged) == (0, 1)
    assert await db_session.scalar(select(func.count()).select_from(QuranVerseHistory)) == 0


async def test_a_truncated_feed_is_followed_from_the_date_of_its_last_row(db_session, tmp_path):
    await _store(db_session)
    fake = FakeQuranpedia(
        {
            "/v1/changes?since=2026-10-03": _feed(
                [_row(1, 1, "2026-10-03 10:00:00", mushaf=6), _row(30, 50, "2026-10-04 08:00:00")],
                truncated=True,
            ),
            "/v1/changes?since=2026-10-04": _feed(
                [_row(30, 50, "2026-10-04 09:00:00"), _row(112, 1, "2026-10-04 09:00:00")],
                since="2026-10-04",
            ),
            "/v1/mushafs/2/30/50": _verse_answer(30, 50),
            "/v1/mushafs/2/112/1": _verse_answer(112, 1),
        }
    )

    report = await sync_quran(db_session, fake.client(), cache_dir=tmp_path)

    assert (report.changed_rows, report.corrected, report.unchanged) == (2, 1, 1)
    assert (await _verse_30_50(db_session)).source_version == "change:2026-10-04 09:00:00"
    # An unchanged text still takes the quranpedia id and page the refetch gave.
    ikhlas = (
        await db_session.scalars(
            select(QuranVerse).where(QuranVerse.surah == 112, QuranVerse.ayah == 1)
        )
    ).one()
    assert (ikhlas.quranpedia_ayah_id, ikhlas.page, ikhlas.text) == (1, 1, verse_text(112, 1))


@pytest.mark.parametrize("too_many", [False, True])
async def test_the_dump_replaces_refetching_when_the_feed_cannot_be_read_whole_or_is_long(
    db_session, tmp_path, monkeypatch, too_many
):
    await _store(db_session)
    monkeypatch.setattr(quran, "COMPLETE_SURAHS", 4)
    monkeypatch.setattr(quran, "COMPLETE_VERSES", 18)
    if too_many:
        monkeypatch.setattr(quran_sync, "MAX_REFETCH", 0)
        feed = _feed([_row(30, 50)])
    else:
        feed = _feed([_row(30, 50, "2026-10-03 10:00:00")] * 2, truncated=True)
    fake = FakeQuranpedia({"/v1/changes": feed, **dump_routes()})

    report = await sync_quran(db_session, fake.client(), cache_dir=tmp_path)

    verse = await _verse_30_50(db_session)
    state = await db_session.get(ScriptureSyncState, quran.SYNC_SOURCE)
    assert (report.via_dump, report.corrected) == ("2026-10-03", 1)
    assert (verse.text, verse.source_version) == (verse_text(30, 50), "dump:2026-10-03")
    assert state is not None
    assert state.dump_version == "2026-10-03"
    assert not any(r.url.path.startswith("/v1/mushafs") for r in fake.requests)


class RefreshCounter:
    """Counts the rebuilds of the verse spans the database is asked for."""

    def __init__(self, engine) -> None:
        self.engine = engine.sync_engine
        self.count = 0

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._seen)
        return self

    def __exit__(self, *_exc) -> None:
        event.remove(self.engine, "before_cursor_execute", self._seen)

    def _seen(self, _conn, _cursor, statement, *_rest) -> None:
        if statement.lstrip().startswith("REFRESH MATERIALIZED VIEW"):
            self.count += 1


async def _spans_follow_the_search_copies(session) -> None:
    rows = (
        await session.execute(
            select(QuranVerseSearch.guard_text, quran_verse_spans.c.guard_text).join(
                quran_verse_spans, quran_verse_spans.c.verse_id == QuranVerseSearch.verse_id
            )
        )
    ).all()
    assert len(rows) == 18
    assert all(span == guard or span.startswith(f"{guard} ") for guard, span in rows)


@pytest.mark.parametrize("via_dump", [False, True])
async def test_several_corrections_rebuild_the_verse_spans_once(
    db_session, engine, tmp_path, monkeypatch, via_dump
):
    await _store(db_session, stale_2_49=True)
    # Emptied first, so only a real rebuild can fill it again.
    await db_session.execute(text("REFRESH MATERIALIZED VIEW quran_verse_spans WITH NO DATA"))
    if via_dump:
        monkeypatch.setattr(quran, "COMPLETE_SURAHS", 4)
        monkeypatch.setattr(quran, "COMPLETE_VERSES", 18)
        monkeypatch.setattr(quran_sync, "MAX_REFETCH", 0)
    routes = {
        "/v1/changes": _feed([_row(2, 49), _row(30, 50)]),
        "/v1/mushafs/2/2/49": _verse_answer(2, 49),
        "/v1/mushafs/2/30/50": _verse_answer(30, 50),
        **dump_routes(),
    }

    with RefreshCounter(engine) as refreshes:
        report = await sync_quran(db_session, FakeQuranpedia(routes).client(), cache_dir=tmp_path)
        rebuilt = refreshes.count
        # Nothing left to correct: the spans are not rebuilt for nothing.
        again = await sync_quran(db_session, FakeQuranpedia(routes).client(), cache_dir=tmp_path)

    assert (report.corrected, again.corrected) == (2, 0)
    # One rebuild a batch, of the spans of each spelling.
    assert (rebuilt, refreshes.count) == (2, 2)
    corrected = {
        verse.id: verse
        for verse in await db_session.scalars(
            select(QuranVerse).where(QuranVerse.surah.in_([2, 30]), QuranVerse.ayah.in_([49, 50]))
        )
    }
    assert {(v.surah, v.ayah): v.text for v in corrected.values()} == {
        (2, 49): verse_text(2, 49),
        (30, 50): verse_text(30, 50),
    }
    spans = dict(
        (
            await db_session.execute(
                select(quran_verse_spans.c.verse_id, quran_verse_spans.c.guard_text)
            )
        ).all()
    )
    standard_spans = dict(
        (
            await db_session.execute(
                select(
                    quran_verse_standard_spans.c.verse_id, quran_verse_standard_spans.c.guard_text
                )
            )
        ).all()
    )
    for verse_id, verse in corrected.items():
        assert spans[verse_id].startswith(guard_fold(verse.text))
        kept = await db_session.get(QuranVerseStandardGuard, verse_id)
        assert kept is not None
        assert kept.guard_text == standard_skeleton(verse.text)
        assert standard_spans[verse_id].startswith(kept.guard_text)
    await _spans_follow_the_search_copies(db_session)


async def test_a_partial_dump_is_never_synced_from(db_session, tmp_path, monkeypatch):
    await _store(db_session)
    monkeypatch.setattr(quran_sync, "MAX_REFETCH", 0)
    fake = FakeQuranpedia({"/v1/changes": _feed([_row(30, 50)]), **dump_routes()})

    with pytest.raises(SyncError, match="not a whole mushaf"):
        await sync_quran(db_session, fake.client(), cache_dir=tmp_path)


async def test_a_verse_the_store_lacks_is_an_error(db_session, tmp_path):
    await _store(db_session)
    fake = FakeQuranpedia(
        {"/v1/changes": _feed([_row(2, 3)]), "/v1/mushafs/2/2/3": _verse_answer(2, 2)}
    )
    fake.routes["/v1/mushafs/2/2/3"] = json_response(
        {"id": 1, "number": 3, "surah": "2", "page_number": 2, "text": verse_text(2, 2)}
    )

    with pytest.raises(SyncError, match="2:3, which the store does not hold"):
        await sync_quran(db_session, fake.client(), cache_dir=tmp_path)


async def test_the_sync_needs_an_imported_quran(db_session, tmp_path):
    with pytest.raises(SyncError, match="import the Quran first"):
        await sync_quran(db_session, FakeQuranpedia({}).client(), cache_dir=tmp_path)


async def test_a_second_process_steps_aside_while_one_syncs(db_session, engine, tmp_path):
    await _store(db_session)
    async with engine.connect() as other, other.begin():
        await other.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": quran_sync.SYNC_LOCK_KEY}
        )
        fake = FakeQuranpedia({})

        report = await sync_quran(db_session, fake.client(), cache_dir=tmp_path)

    assert report.skipped
    assert report.since == "2026-10-03"
    assert fake.requests == []


async def test_collecting_changes_keeps_the_latest_row_of_each_verse():
    fake = FakeQuranpedia(
        {
            "/v1/changes": _feed(
                [_row(30, 50, "2026-10-03 10:00:00"), _row(30, 50, "2026-10-03 11:00:00")]
            )
        }
    )

    rows, until, complete = await collect_changes(fake.client(), date(2026, 10, 3))

    assert [row.changed_at for row in rows] == ["2026-10-03 11:00:00"]
    assert (until, complete) == (UNTIL, True)


async def test_the_command_reports_a_sync_and_its_failures(scripture_maker, tmp_path, capsys):
    async with scripture_maker() as session, session.begin():
        await _store(session)
    routes = {"/v1/changes": _feed([_row(30, 50)]), "/v1/mushafs/2/30/50": _verse_answer(30, 50)}
    argv = ["--cache-dir", str(tmp_path)]

    done = await sync_command.run(argv, sessionmaker=scripture_maker, http=_http(routes))
    failed = await sync_command.run(
        argv, sessionmaker=scripture_maker, http=_http({"/v1/changes": httpx.Response(500)})
    )

    captured = capsys.readouterr()
    assert (done, failed) == (0, 1)
    assert "1 corrected (30:50), 0 unchanged; next run from 2026-10-05" in captured.out
    assert "sync failed: GET https://api.quranpedia.net/v1/changes answered 500" in captured.err
    async with scripture_maker() as session:
        state = await session.get(ScriptureSyncState, quran.SYNC_SOURCE)
        assert state is not None
        assert state.synced_through == date(2026, 10, 5)


async def test_the_command_says_when_it_stepped_aside_or_read_a_dump(
    scripture_maker, engine, tmp_path, capsys, monkeypatch
):
    async with scripture_maker() as session, session.begin():
        await _store(session)
    monkeypatch.setattr(quran, "COMPLETE_SURAHS", 4)
    monkeypatch.setattr(quran, "COMPLETE_VERSES", 18)
    monkeypatch.setattr(quran_sync, "MAX_REFETCH", 0)
    routes = {"/v1/changes": _feed([_row(30, 50)]), **dump_routes()}

    async with engine.connect() as other, other.begin():
        await other.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": quran_sync.SYNC_LOCK_KEY}
        )
        aside = await sync_command.run(
            ["--cache-dir", str(tmp_path)], sessionmaker=scripture_maker, http=_http({})
        )
    via_dump = await sync_command.run(
        ["--cache-dir", str(tmp_path)], sessionmaker=scripture_maker, http=_http(routes)
    )

    out = capsys.readouterr().out
    assert (aside, via_dump) == (0, 0)
    assert "another sync is running" in out
    assert "from dump 2026-10-03, 1 corrected (none)" in out


async def test_the_command_uses_the_application_database_when_none_is_given(monkeypatch, tmp_path):
    disposed: list[bool] = []

    async def dispose() -> None:
        disposed.append(True)

    monkeypatch.setattr(sync_command, "dispose_engine", dispose)

    code = await sync_command.run(["--cache-dir", str(tmp_path)], http=_http({}))

    assert code == 1
    assert disposed == [True]


def test_main_runs_the_command(monkeypatch):
    async def fake_run(argv):
        return 3

    monkeypatch.setattr(sync_command, "run", fake_run)

    assert sync_command.main([]) == 3


def _http(routes) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(FakeQuranpedia(routes).handler))
