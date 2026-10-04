"""The committed `data/masar/tabsira-masar-1.0.json`: valid, complete, and what masar.md produces."""

from __future__ import annotations

import hashlib

from src.cli import parse_masar, validate_masar
from src.schemas.learning_path import dumps
from src.services.masar_validator import read_path
from tests.support_ontology import REAL_MASAR, REAL_MASAR_JSON


def test_the_committed_json_is_what_the_document_produces(real_path):
    # If this fails the document changed: run `python -m src.cli.parse_masar` in apps/api and
    # commit the new JSON with it (or add a new path version for a new release).
    assert REAL_MASAR_JSON.read_text(encoding="utf-8") == dumps(real_path)


def test_the_committed_json_names_the_document_it_was_made_from(real_path):
    path = read_path(REAL_MASAR_JSON)

    assert path.source.file == "docs/spec/masar.md"
    assert path.source.sha256 == hashlib.sha256(REAL_MASAR.read_bytes()).hexdigest()
    assert path.path_version == "tabsira-masar-1.0" == REAL_MASAR_JSON.stem


def test_the_committed_json_is_valid_and_has_sixteen_domains_and_ninety_six_units():
    path = read_path(REAL_MASAR_JSON, expected_domains=16, expected_units=96)

    assert [d.id for d in path.domains][:2] == ["T00", "T01"]
    assert len({u.id for u in path.units}) == 96
    assert all(len(u.prerequisites) <= 3 for u in path.units)


def test_the_commands_agree_that_the_committed_json_is_valid_and_current(capsys):
    assert (
        validate_masar.main(
            [str(REAL_MASAR_JSON), "--expect-domains", "16", "--expect-units", "96"]
        )
        == 0
    )
    assert capsys.readouterr().out == (
        "valid: tabsira-masar-1.0, 16 domains, 96 units, 6 depths, 8 coverage rules\n"
    )

    code = parse_masar.main(["--source", str(REAL_MASAR), "--out", str(REAL_MASAR_JSON), "--check"])

    assert code == 0
    assert "is up to date" in capsys.readouterr().out
