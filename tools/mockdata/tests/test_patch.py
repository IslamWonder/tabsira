from __future__ import annotations

import argparse
from typing import Any

import pytest

from mockdata import patch

SCENE = {"labels": ["cat"], "ar": "قطة"}
BODY = {
    "quran": {"surah": 2, "ayah": 164},
    "hadith": {"collection": "bukhari", "number": "1"},
    "title": "t",
}


def test_ids_are_whole_numbers_separated_by_commas() -> None:
    assert patch.parse_ids("12, 40,7,") == frozenset({7, 12, 40})
    for bad in ("", ",", "a,2", "0", "-3", "1.5"):
        with pytest.raises(argparse.ArgumentTypeError):
            patch.parse_ids(bad)


def test_evidence_is_named_by_reference_only() -> None:
    assert patch.evidence_of(None) is None
    assert patch.evidence_of(BODY) == {"quran": "2:164", "hadith": "bukhari:1"}
    assert patch.evidence_of({"quran": None, "hadith": None}) == {"quran": None, "hadith": None}


def test_a_result_says_what_became_of_the_insight() -> None:
    assert patch.result_of(BODY, None, scene=False) == patch.EMPTIED
    assert patch.result_of(None, BODY, scene=False) == patch.FILLED
    assert patch.result_of(BODY, BODY | {"title": "u"}, scene=False) == patch.REPLACED
    assert patch.result_of(BODY, BODY, scene=True) == patch.REPLACED
    assert patch.result_of(BODY, BODY, scene=False) == patch.UNCHANGED
    assert patch.result_of(None, None, scene=False) == patch.UNCHANGED


def test_only_the_listed_photos_are_touched() -> None:
    other = {"placepix_id": 5, "scene": SCENE, "insight": BODY}
    document: dict[str, Any] = {
        "images": [{"placepix_id": 1, "scene": SCENE, "insight": BODY}, other],
        "posts": [{"ref": "p1"}],
    }
    entries: dict[str, dict[str, Any]] = {
        "1": {"outcome": "insights", "scene": SCENE, "insight": BODY | {"title": "u"}},
        "5": {"outcome": "people", "scene": SCENE, "insight": None},
        "8": {"outcome": "insights", "scene": SCENE, "insight": BODY},
    }
    changes = patch.patch_images(document, entries, frozenset({1, 8}))
    assert [(c["photo"], c["result"]) for c in changes] == [(1, "replaced"), (8, "not_in_file")]
    assert document["images"][0]["insight"]["title"] == "u"
    assert document["images"][1] is other
    assert other["insight"] == BODY
    assert document["posts"] == [{"ref": "p1"}]
    assert patch.changed(changes) == [1]
