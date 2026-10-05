from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
import pytest

from mockdata import catalogue, cli, places
from mockdata.catalogue import Photo
from mockdata.places import Gazetteer

from .test_places import FakeConn


def test_database_url_prefers_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1/db")
    assert cli.database_url(tmp_path / "none") == "postgresql://u:p@127.0.0.1/db"


def test_database_url_from_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env = tmp_path / ".env"
    env.write_text("A=1\nDATABASE_URL='postgresql://u@127.0.0.1/db'\n", encoding="utf-8")
    assert cli.database_url(env) == "postgresql://u@127.0.0.1/db"


def test_database_url_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit, match="DATABASE_URL"):
        cli.database_url(tmp_path / "none")


def test_connect_read_only_sets_the_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    class Conn:
        read_only = False

    seen: dict[str, Any] = {}

    def fake_connect(url: str, autocommit: bool) -> Conn:
        seen.update(url=url, autocommit=autocommit)
        return Conn()

    monkeypatch.setattr(psycopg, "connect", fake_connect)
    conn = cli.connect_read_only("postgresql://x")
    assert conn.read_only is True  # type: ignore[attr-defined]
    assert seen == {"url": "postgresql://x", "autocommit": True}


def test_fetch_photos_uses_the_catalogue_fetcher(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        catalogue, "fetch_catalogue", lambda client: [Photo(1, "a.jpg", "cat", 1, 1)]
    )
    assert cli.fetch_photos() == [Photo(1, "a.jpg", "cat", 1, 1)]


def test_resolve_now() -> None:
    assert cli.resolve_now("2026-10-05T10:00:00Z") == datetime(2026, 10, 5, 10)
    assert cli.resolve_now(None).microsecond == 0


def test_defaults_come_from_the_plan_and_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MOCK_SEED", raising=False)
    monkeypatch.delenv("MOCK_MEMBERS", raising=False)
    args = cli.parser().parse_args([])
    assert (args.seed, args.members) == (42, 1000)
    assert (args.insights, args.posts, args.follows) == (2000, 1200, 15000)
    assert (args.reactions, args.comments, args.map_entries) == (30000, 4000, 900)
    assert args.out.name == "tabsira-mock-v1.json"
    assert args.out.parent.name == "mock"
    monkeypatch.setenv("MOCK_SEED", "7")
    assert cli.parser().parse_args([]).seed == 7


def write_library(path: Path, photos: list[Photo]) -> Path:
    """A photo library where every photo but the last gave an insight (values invented)."""
    entries = {
        str(p.id): {
            "filename": p.filename,
            "category": p.category,
            "width": p.width,
            "height": p.height,
            "outcome": "insights" if n < len(photos) - 1 else "people",
            "insight": {"title": f"t{p.id}"} if n < len(photos) - 1 else None,
        }
        for n, p in enumerate(photos)
    }
    path.write_text(json.dumps({"version": 1, "photos": entries, "runs": []}), encoding="utf-8")
    return path


def run(tmp_path: Path, extra: list[str], photos: list[Photo], conn: FakeConn) -> int:
    return cli.main(
        [
            "--members", "220", "--now", "2026-10-05T10:00:00Z",
            "--insights", "30", "--posts", "20", "--follows", "50", "--reactions", "50",
            "--comments", "20", "--map-entries", "10",
            "--out", str(tmp_path / "o.json"),
            "--photos-from", str(write_library(tmp_path / "lib.json", photos)),
            "--places-cache", str(tmp_path / "pl.json"),
            "--env-file", str(tmp_path / "env"),
            *extra,
        ],
        connect=lambda url: conn,
    )  # fmt: skip


def test_main_end_to_end_with_caches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    photos: list[Photo],
    gazetteer: Gazetteer,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u@127.0.0.1/db")
    # The fake database knows two cities; extend it to cover the 22 countries of the plan.
    conn = FakeConn()
    monkeypatch.setattr(places, "fetch_gazetteer", lambda c: gazetteer)
    assert run(tmp_path, [], [*photos, Photo(900, "people.jpg", "city", 1, 1)], conn) == 0
    summary = capsys.readouterr().out
    assert "220 members" in summary
    data = json.loads((tmp_path / "o.json").read_text(encoding="utf-8"))
    assert len(data["members"]) == 220
    assert 900 not in {i["placepix_id"] for i in data["images"]}
    assert all(i["insight"] == {"title": f"t{i['placepix_id']}"} for i in data["images"])
    first = (tmp_path / "o.json").read_bytes()

    # Second run: both caches exist, so neither the network nor the database is touched.
    def boom(*_: object) -> Any:
        raise AssertionError("cache not used")

    monkeypatch.setattr(places, "fetch_gazetteer", boom)
    assert cli.main(
        ["--members", "220", "--now", "2026-10-05T10:00:00Z", "--insights", "30",
         "--posts", "20", "--follows", "50", "--reactions", "50", "--comments", "20",
         "--map-entries", "10", "--out", str(tmp_path / "o.json"),
         "--photos-from", str(tmp_path / "lib.json"), "--places-cache", str(tmp_path / "pl.json")],
        connect=boom,
    ) == 0  # fmt: skip
    assert (tmp_path / "o.json").read_bytes() == first


def test_refresh_places_refetches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, photos: list[Photo], gazetteer: Gazetteer
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u@127.0.0.1/db")
    calls: list[str] = []

    def fetch_places(_: object) -> Gazetteer:
        calls.append("places")
        return gazetteer

    monkeypatch.setattr(places, "fetch_gazetteer", fetch_places)
    library = write_library(tmp_path / "lib.json", photos)
    for _ in range(2):
        cli.main(
            ["--members", "220", "--now", "2026-10-05T10:00:00Z", "--insights", "5",
             "--out", str(tmp_path / "o.json"), "--photos-from", str(library),
             "--places-cache", str(tmp_path / "p.json"), "--refresh-places"],
            connect=lambda url: FakeConn(),
        )  # fmt: skip
    assert calls == ["places", "places"]


def test_the_photo_library_is_needed(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="make mock-photos"):
        cli.main(["--photos-from", str(tmp_path / "none.json")])
