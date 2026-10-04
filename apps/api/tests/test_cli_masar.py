"""The two commands of the learning path: parse the reference into data, and validate a data file."""

from __future__ import annotations

import subprocess
import sys

import pytest

from src.cli import parse_masar, validate_masar
from src.schemas.learning_path import dumps
from tests.support_ontology import API_DIR, REAL_MASAR

SOURCE = str(REAL_MASAR)


# ─── parse_masar ───


def test_the_document_is_parsed_and_the_json_written_where_asked(capsys, tmp_path, real_path):
    target = tmp_path / "out" / "path.json"

    code = parse_masar.main(["--source", SOURCE, "--out", str(target)])

    out = capsys.readouterr()
    assert code == 0
    assert "learning path tabsira-masar-1.0: 16 domains, 96 units" in out.out
    assert f"wrote {target}" in out.out
    # Byte for byte: a CRLF written on Windows would change a tracked file.
    assert target.read_bytes() == dumps(real_path).encode("utf-8")
    assert out.err == ""


def test_the_source_is_recorded_relative_to_the_repository_when_it_is_inside_it(tmp_path):
    assert parse_masar._recorded_name(REAL_MASAR) == "docs/spec/masar.md"
    assert parse_masar._recorded_name(tmp_path / "elsewhere.md") == "elsewhere.md"


def test_the_default_target_is_named_after_the_path_version(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(parse_masar, "DEFAULT_OUT_DIR", tmp_path)

    assert parse_masar.main(["--source", SOURCE]) == 0

    assert (tmp_path / "tabsira-masar-1.0.json").exists()
    assert "wrote" in capsys.readouterr().out


def test_the_path_version_and_the_expected_counts_can_be_given(capsys, tmp_path):
    code = parse_masar.main(
        [
            "--source",
            SOURCE,
            "--path-version",
            "tabsira-masar-1.1",
            "--expect-domains",
            "16",
            "--expect-units",
            "96",
            "--out",
            str(tmp_path / "x.json"),
        ]
    )

    assert code == 0
    assert "learning path tabsira-masar-1.1" in capsys.readouterr().out


def test_wrong_expected_counts_fail_and_write_nothing(capsys, tmp_path):
    code = parse_masar.main(
        ["--source", SOURCE, "--expect-units", "97", "--out", str(tmp_path / "x.json")]
    )

    err = capsys.readouterr().err
    assert code == 1
    assert "97 units were expected, the file holds 96." in err
    assert not (tmp_path / "x.json").exists()


def test_a_document_that_cannot_be_parsed_exits_one_with_its_problems(capsys, tmp_path):
    broken = tmp_path / "broken.md"
    broken.write_text("# x\n", encoding="utf-8")

    code = parse_masar.main(["--source", str(broken), "--out", str(tmp_path / "x.json")])

    err = capsys.readouterr().err
    assert code == 1
    assert "masar.md cannot be parsed" in err
    assert "The document gives no «الإصدار»." in err


def test_a_document_that_cannot_be_read_exits_one(capsys, tmp_path):
    assert parse_masar.main(["--source", str(tmp_path / "absent.md")]) == 1
    assert "Cannot read" in capsys.readouterr().err


def test_check_passes_when_the_json_is_what_the_document_produces(capsys, tmp_path):
    target = tmp_path / "path.json"
    assert parse_masar.main(["--source", SOURCE, "--out", str(target)]) == 0
    capsys.readouterr()

    code = parse_masar.main(["--source", SOURCE, "--out", str(target), "--check"])

    assert code == 0
    assert "is up to date" in capsys.readouterr().out


def test_check_fails_for_a_stale_or_a_missing_file_and_writes_nothing(capsys, tmp_path):
    stale = tmp_path / "stale.json"
    stale.write_text("{}\n", encoding="utf-8")

    for target in (stale, tmp_path / "missing.json"):
        assert parse_masar.main(["--source", SOURCE, "--out", str(target), "--check"]) == 1

    assert (
        "is not what masar.md produces. Run the command without --check." in capsys.readouterr().err
    )
    assert stale.read_text(encoding="utf-8") == "{}\n"
    assert not (tmp_path / "missing.json").exists()


# ─── validate_masar ───


def test_a_valid_file_is_reported_with_its_counts(capsys, tmp_path, real_path):
    good = tmp_path / "good.json"
    good.write_text(dumps(real_path), encoding="utf-8")

    code = validate_masar.main([str(good), "--expect-domains", "16", "--expect-units", "96"])

    assert code == 0
    assert capsys.readouterr().out == (
        "valid: tabsira-masar-1.0, 16 domains, 96 units, 6 depths, 8 coverage rules\n"
    )


def test_a_wrong_expected_count_fails(capsys, tmp_path, real_path):
    good = tmp_path / "good.json"
    good.write_text(dumps(real_path), encoding="utf-8")

    assert validate_masar.main([str(good), "--expect-units", "95"]) == 1
    assert "95 units were expected, the file holds 96." in capsys.readouterr().err


def test_an_invalid_file_exits_one_and_lists_the_problems(capsys, tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{}", encoding="utf-8")

    code = validate_masar.main([str(broken)])

    err = capsys.readouterr().err
    assert code == 1
    assert "The learning path file is not valid" in err
    assert "path_version: Field required" in err


@pytest.mark.parametrize("module", ["src.cli.parse_masar", "src.cli.validate_masar"])
def test_each_module_runs_as_a_command(module, tmp_path):
    arguments = (
        ["--source", str(tmp_path / "absent.md")]
        if module.endswith("parse_masar")
        else [str(tmp_path / "absent.json")]
    )

    result = subprocess.run(
        [sys.executable, "-m", module, *arguments],
        cwd=API_DIR,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 1
    assert "Cannot read" in result.stderr
