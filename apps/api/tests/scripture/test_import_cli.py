"""The import command: steps in order, idempotent, and a failed step reported and rolled back."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import func, select

from src.cli import import_scripture
from src.models import QuranVerse
from src.scripture import quran
from src.scripture.quranpedia import fetch_dump_files
from tests.scripture.fake_http import FakeQuranpedia, dump_routes
from tests.scripture.fixtures import load_json


def _whole(monkeypatch) -> None:
    """Let the fixture dump, a few surahs only, pass for a whole mushaf."""
    raw = load_json("quranpedia-mushafs-2.json")["data"]["surahs"]
    monkeypatch.setattr(quran, "COMPLETE_SURAHS", len(raw))
    monkeypatch.setattr(quran, "COMPLETE_VERSES", sum(len(s["ayahs"]) for s in raw))


def _http(routes) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(FakeQuranpedia(routes).handler))


async def _count(maker) -> int:
    async with maker() as session:
        return int(await session.scalar(select(func.count()).select_from(QuranVerse)) or 0)


async def test_download_then_quran_imports_the_verified_dump(
    tmp_path, scripture_maker, monkeypatch, capsys
):
    _whole(monkeypatch)
    argv = ["download", "quran", "--cache-dir", str(tmp_path), "--corpus-dir", str(tmp_path)]

    first = await import_scripture.run(
        argv, sessionmaker=scripture_maker, http=_http(dump_routes())
    )
    second = await import_scripture.run(
        argv, sessionmaker=scripture_maker, http=_http(dump_routes())
    )

    out = capsys.readouterr().out
    assert (first, second) == (0, 0)
    assert await _count(scripture_maker) == quran.COMPLETE_VERSES
    assert "download: quranpedia dump 2026-10-03 verified" in out
    assert f"{quran.COMPLETE_VERSES} inserted" in out
    assert f"0 inserted, 0 corrected, {quran.COMPLETE_VERSES} unchanged" in out


async def test_without_network_a_verified_cached_dump_is_kept(tmp_path, scripture_maker, capsys):
    await fetch_dump_files(FakeQuranpedia(dump_routes()).client(), tmp_path)
    offline = {"/dumps/manifest.json": httpx.Response(503)}

    code = await import_scripture.run(
        ["download", "--cache-dir", str(tmp_path)],
        sessionmaker=scripture_maker,
        http=_http(offline),
    )

    assert code == 0
    assert "2026-10-03 verified" in capsys.readouterr().out


async def test_without_network_or_cache_the_download_fails(tmp_path, scripture_maker, capsys):
    offline = {"/dumps/manifest.json": httpx.Response(503)}

    code = await import_scripture.run(
        ["download", "--cache-dir", str(tmp_path)],
        sessionmaker=scripture_maker,
        http=_http(offline),
    )

    assert code == 1
    assert "import failed: GET https://api.quranpedia.net/dumps/manifest.json answered 503" in (
        capsys.readouterr().err
    )


async def test_the_quran_step_needs_a_verified_whole_dump(tmp_path, scripture_maker, capsys):
    argv = ["quran", "--cache-dir", str(tmp_path)]

    missing = await import_scripture.run(argv, sessionmaker=scripture_maker, http=_http({}))
    await fetch_dump_files(FakeQuranpedia(dump_routes()).client(), tmp_path)
    partial = await import_scripture.run(argv, sessionmaker=scripture_maker, http=_http({}))

    err = capsys.readouterr().err
    assert (missing, partial) == (1, 1)
    assert "run the download step first" in err
    assert "is not a whole mushaf" in err
    assert await _count(scripture_maker) == 0


async def test_an_unknown_step_stops_before_anything_runs(capsys):
    with pytest.raises(SystemExit) as exit_info:
        await import_scripture.run(["download", "nothing"])

    assert exit_info.value.code == 2
    assert "unknown step nothing" in capsys.readouterr().err


async def test_the_command_uses_the_application_database_when_none_is_given(tmp_path, monkeypatch):
    disposed: list[bool] = []

    async def dispose() -> None:
        disposed.append(True)

    monkeypatch.setattr(import_scripture, "dispose_engine", dispose)

    code = await import_scripture.run(["quran", "--cache-dir", str(tmp_path)], http=_http({}))

    assert code == 1
    assert disposed == [True]


def test_main_runs_the_command_with_its_arguments(monkeypatch):
    seen: list[list[str]] = []

    async def fake_run(argv):
        seen.append(argv)
        return 7

    monkeypatch.setattr(import_scripture, "run", fake_run)

    assert import_scripture.main(["quran"]) == 7
    assert seen == [["quran"]]
