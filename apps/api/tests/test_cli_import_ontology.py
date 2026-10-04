"""The command that imports the ontology: its report, its files and its exit codes."""

from __future__ import annotations

import subprocess
import sys

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from src.cli import import_ontology
from src.cli.import_ontology import Options, execute, main
from src.config import ConfigError
from src.models import OntologyEntity
from src.services.ontology_import import export_json
from tests.support_ontology import API_DIR, REAL_WORKBOOK, good_row, workbook_bytes


def options(source=REAL_WORKBOOK, **changes) -> Options:
    values = {"source": source, "json_path": None, "expected_count": 1000, "load_database": False}
    return Options(**{**values, **changes})


@pytest.fixture
def small_workbook(tmp_path):
    path = tmp_path / "small.xlsx"
    path.write_bytes(workbook_bytes([good_row(1), good_row(2, label_ar="شيء 1")]))
    return path


async def test_validating_reports_the_workbook_and_writes_nothing(capsys, tmp_path):
    code = await execute(options(json_path=None, load_database=False))

    out = capsys.readouterr()
    assert code == 0
    assert "ontology: world-ontology.xlsx, sheet «الكيان ومفاهيمه»" in out.out
    assert "sha256 687c3815b5c6daf24154a2ce91bcbfe4cbdb7e49b9633fcf60c38135438ec5c9" in out.out
    assert "valid: 1000 entities, 43 domains" in out.out
    assert "constraint  123  تأكيد معنى المشهد" in out.out
    assert "done in" in out.out
    assert out.err == ""
    assert list(tmp_path.iterdir()) == []


async def test_the_json_is_written_where_asked_and_its_folder_is_made(
    capsys, tmp_path, real_ontology
):
    target = tmp_path / "generated" / "ontology.json"

    code = await execute(options(json_path=target))

    assert code == 0
    assert target.read_text(encoding="utf-8") == export_json(real_ontology)
    assert f"json: wrote {target}" in capsys.readouterr().out


async def test_warnings_go_to_the_error_stream(capsys, tmp_path):
    path = tmp_path / "twins.xlsx"
    path.write_bytes(workbook_bytes([good_row(1), good_row(2, label_ar="شيء 1")]))

    code = await execute(options(source=path, expected_count=2))

    out = capsys.readouterr()
    assert code == 0
    assert "warning: E002 has the same label as E001" in out.err


async def test_a_broken_workbook_exits_one_and_lists_every_problem(capsys, tmp_path):
    path = tmp_path / "broken.xlsx"
    path.write_bytes(workbook_bytes([good_row(1, domain=None), good_row(2, id="X2")]))

    code = await execute(options(source=path, json_path=tmp_path / "out.json", expected_count=2))

    out = capsys.readouterr()
    assert code == 1
    assert out.out == ""
    assert "The ontology workbook is not valid" in out.err
    assert "Row 5, column «المجال» (F): is empty." in out.err
    assert "Row 6, column «المعرّف» (G): «X2» is not an id of the form E001." in out.err
    assert not (tmp_path / "out.json").exists()


async def test_a_missing_file_exits_one(capsys, tmp_path):
    code = await execute(options(source=tmp_path / "nothing.xlsx"))

    assert code == 1
    assert "Cannot read" in capsys.readouterr().err


async def test_loading_reports_the_counts_and_leaves_the_rows_in_the_table(capsys, session_factory):
    code = await execute(options(load_database=True), session_factory)

    assert code == 0
    assert "database: 1000 inserted, 0 updated, 0 removed" in capsys.readouterr().out
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(OntologyEntity)) == 1000

    again = await execute(options(load_database=True), session_factory)

    assert again == 0
    assert "database: 0 inserted, 1000 updated, 0 removed" in capsys.readouterr().out


async def test_a_database_that_cannot_be_loaded_exits_one_without_its_error_text(
    capsys, small_workbook
):
    class Broken:
        def __call__(self):
            raise OperationalError("INSERT secret", {}, Exception("password=hunter2"))

    code = await execute(
        options(source=small_workbook, expected_count=2, load_database=True), Broken()
    )

    err = capsys.readouterr().err
    assert code == 1
    assert "Cannot load the ontology into the database (OperationalError)" in err
    assert "make migrate" in err
    assert "hunter2" not in err


async def test_a_missing_database_setting_is_reported_without_a_traceback(
    monkeypatch, capsys, small_workbook
):
    def sessionmaker():
        raise ConfigError("Invalid configuration, fix the .env:\n  - DATABASE_URL: Field required")

    monkeypatch.setattr(import_ontology, "get_sessionmaker", sessionmaker)

    code = await execute(options(source=small_workbook, expected_count=2, load_database=True))

    assert code == 1
    assert "DATABASE_URL: Field required" in capsys.readouterr().err


async def test_without_a_session_factory_the_applications_engine_is_used_and_closed(
    monkeypatch, session_factory, small_workbook
):
    closed = []

    async def dispose():
        closed.append(True)

    monkeypatch.setattr(import_ontology, "get_sessionmaker", lambda: session_factory)
    monkeypatch.setattr(import_ontology, "dispose_engine", dispose)

    code = await execute(options(source=small_workbook, expected_count=2, load_database=True))

    assert (code, closed) == (0, [True])


async def test_the_engine_is_closed_even_when_the_load_fails(monkeypatch, small_workbook):
    closed = []

    async def dispose():
        closed.append(True)

    def refused():
        raise OSError("connection refused")

    monkeypatch.setattr(import_ontology, "get_sessionmaker", lambda: refused)
    monkeypatch.setattr(import_ontology, "dispose_engine", dispose)

    code = await execute(options(source=small_workbook, expected_count=2, load_database=True))

    assert (code, closed) == (1, [True])


# ─── The command line ───
# `main` starts its own event loop, so these are plain tests and use no database.


def test_validate_only_reads_and_writes_nothing(capsys, tmp_path):
    code = main(
        ["--source", str(REAL_WORKBOOK), "--json", str(tmp_path / "x.json"), "--validate-only"]
    )

    assert code == 0
    assert "valid: 1000 entities" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []


def test_no_db_and_no_json_leave_only_the_report(capsys, tmp_path):
    assert main(["--source", str(REAL_WORKBOOK), "--no-db", "--no-json"]) == 0
    assert (
        main(["--source", str(REAL_WORKBOOK), "--no-db", "--json", str(tmp_path / "y.json")]) == 0
    )

    assert (tmp_path / "y.json").exists()
    assert capsys.readouterr().out.count("valid: 1000 entities") == 2


def test_the_expected_count_is_an_argument(capsys, small_workbook):
    assert main(["--source", str(small_workbook), "--expected-count", "2", "--validate-only"]) == 0
    assert main(["--source", str(small_workbook), "--validate-only"]) == 1

    assert "The sheet has 2 entities, 1000 were expected" in capsys.readouterr().err


def test_the_defaults_point_at_the_workbook_and_the_json_of_the_repository():
    assert import_ontology.DEFAULT_SOURCE == REAL_WORKBOOK
    assert import_ontology.DEFAULT_JSON.parts[-3:] == ("data", "ontology", "world-ontology.json")


def test_the_module_runs_as_a_command_and_exits_one_on_a_broken_file(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "src.cli.import_ontology", "--source", str(tmp_path / "no.xlsx")],
        cwd=API_DIR,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 1
    assert "Cannot read" in result.stderr
