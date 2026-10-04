"""The command that imports a learning path version: its report, its flags and its exit codes."""

from __future__ import annotations

import subprocess
import sys

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from src.cli import import_masar
from src.cli.import_masar import Options, execute, main
from src.config import ConfigError
from src.models import LearningPathVersion, LearningUnit
from src.schemas.learning_path import dumps
from tests.support_ontology import API_DIR, REAL_MASAR_JSON


def options(source=REAL_MASAR_JSON, **changes) -> Options:
    values = {
        "source": source,
        "activate": None,
        "replace": False,
        "expect_domains": 16,
        "expect_units": 96,
    }
    return Options(**{**values, **changes})


@pytest.fixture
def copy_of_the_path(tmp_path, real_path):
    """A writable copy of the learning path file, to edit and import under another name."""
    path = tmp_path / "tabsira-masar-1.1.json"
    path.write_text(
        dumps(real_path).replace("tabsira-masar-1.0", "tabsira-masar-1.1"), encoding="utf-8"
    )
    return path


async def test_the_committed_path_is_imported_and_reported(capsys, session_factory):
    code = await execute(options(), session_factory)

    out = capsys.readouterr()
    assert code == 0
    assert "learning path tabsira-masar-1.0: 16 domains, 96 units" in out.out
    assert "database: created, 16 domains, 96 units, active" in out.out
    assert out.err == ""
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(LearningUnit)) == 96
        stored = await session.get(LearningPathVersion, "tabsira-masar-1.0")
        assert stored.source_file == "tabsira-masar-1.0.json"
        assert stored.is_active is True


async def test_importing_it_again_changes_nothing(capsys, session_factory):
    await execute(options(), session_factory)
    capsys.readouterr()

    code = await execute(options(), session_factory)

    assert code == 0
    assert "database: unchanged, 16 domains, 96 units, active" in capsys.readouterr().out


async def test_a_release_waits_to_be_activated_unless_asked(
    capsys, session_factory, copy_of_the_path
):
    await execute(options(), session_factory)
    capsys.readouterr()

    waiting = await execute(options(copy_of_the_path), session_factory)
    activated = await execute(options(copy_of_the_path, activate=True), session_factory)

    out = capsys.readouterr().out
    assert (waiting, activated) == (0, 0)
    assert "database: created, 16 domains, 96 units, not active" in out
    assert "database: unchanged, 16 domains, 96 units, active" in out


async def test_a_conflicting_file_for_a_published_version_exits_one(
    capsys, session_factory, tmp_path, real_path
):
    await execute(options(), session_factory)
    capsys.readouterr()
    edited = tmp_path / "tabsira-masar-1.0.json"
    edited.write_text(dumps(real_path.model_copy(update={"title": "مسار معدّل"})), encoding="utf-8")

    refused = await execute(options(edited), session_factory)
    replaced = await execute(options(edited, replace=True), session_factory)

    out = capsys.readouterr()
    assert (refused, replaced) == (1, 0)
    assert "already published with other content" in out.err
    assert "database: replaced, 16 domains, 96 units, active" in out.out


async def test_an_invalid_file_exits_one_and_reaches_no_database(capsys, tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{}", encoding="utf-8")

    code = await execute(options(broken), session_factory=None)

    out = capsys.readouterr()
    assert code == 1
    assert out.out == ""
    assert "The learning path file is not valid" in out.err


async def test_wrong_expected_counts_exit_one(capsys):
    code = await execute(options(expect_units=97), None)

    assert code == 1
    assert "97 units were expected, the file holds 96." in capsys.readouterr().err


async def test_a_missing_file_exits_one(capsys, tmp_path):
    code = await execute(options(tmp_path / "absent.json"), None)

    assert code == 1
    assert "Cannot read" in capsys.readouterr().err


async def test_a_database_that_cannot_be_loaded_exits_one_without_its_error_text(capsys):
    class Broken:
        def __call__(self):
            raise OperationalError("INSERT secret", {}, Exception("password=hunter2"))

    code = await execute(options(), Broken())

    err = capsys.readouterr().err
    assert code == 1
    assert "Cannot load the learning path into the database (OperationalError)" in err
    assert "make migrate" in err
    assert "hunter2" not in err


async def test_without_a_session_factory_the_applications_engine_is_used_and_closed(
    monkeypatch, session_factory
):
    closed = []

    async def dispose():
        closed.append(True)

    monkeypatch.setattr(import_masar, "get_sessionmaker", lambda: session_factory)
    monkeypatch.setattr(import_masar, "dispose_engine", dispose)

    code = await execute(options())

    assert (code, closed) == (0, [True])


async def test_a_missing_database_setting_is_reported_without_a_traceback(monkeypatch, capsys):
    def sessionmaker():
        raise ConfigError("Invalid configuration, fix the .env:\n  - DATABASE_URL: Field required")

    monkeypatch.setattr(import_masar, "get_sessionmaker", sessionmaker)

    code = await execute(options())

    assert code == 1
    assert "DATABASE_URL: Field required" in capsys.readouterr().err


# ─── The command line ───


def test_the_flags_are_read_from_the_command_line(monkeypatch):
    seen = []

    async def fake_execute(received):
        seen.append(received)
        return 0

    monkeypatch.setattr(import_masar, "execute", fake_execute)

    assert main(["--source", "x.json", "--activate", "--replace", "--expect-units", "96"]) == 0
    assert main(["--no-activate"]) == 0
    assert main([]) == 0

    assert [(o.activate, o.replace, o.expect_units) for o in seen] == [
        (True, True, 96),
        (False, False, None),
        (None, False, None),
    ]
    assert str(seen[0].source) == "x.json"
    assert seen[2].source == import_masar.DEFAULT_SOURCE == REAL_MASAR_JSON


def test_activate_and_no_activate_exclude_each_other(capsys):
    with pytest.raises(SystemExit):
        main(["--activate", "--no-activate"])

    assert "not allowed with argument" in capsys.readouterr().err


def test_the_module_runs_as_a_command_and_exits_one_on_a_missing_file(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "src.cli.import_masar", "--source", str(tmp_path / "no.json")],
        cwd=API_DIR,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 1
    assert "Cannot read" in result.stderr
