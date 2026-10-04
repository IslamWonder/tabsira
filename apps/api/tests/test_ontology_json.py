"""The generated `data/ontology/world-ontology.json` is what the workbook produces, and small enough to commit."""

from __future__ import annotations

import json

from src.services.ontology_import import export_json
from tests.support_ontology import REAL_JSON, REAL_WORKBOOK

ONE_MEGABYTE = 1_000_000


def test_the_committed_json_is_what_the_workbook_generates(real_ontology):
    # If this fails the workbook changed: run `python -m src.cli.import_ontology --no-db`
    # in apps/api and commit the new JSON with it.
    assert REAL_JSON.read_text(encoding="utf-8") == export_json(real_ontology)


def test_the_committed_json_is_under_a_megabyte():
    assert REAL_JSON.stat().st_size < ONE_MEGABYTE


def test_the_committed_json_names_its_source_and_counts_its_entities():
    document = json.loads(REAL_JSON.read_text(encoding="utf-8"))

    assert document["source"]["file"] == REAL_WORKBOOK.name
    assert len(document["source"]["sha256"]) == 64
    assert document["source"]["entity_count"] == len(document["entities"]) == 1000
