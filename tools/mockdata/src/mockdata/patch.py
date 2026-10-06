"""
Patch the insights of some photos into a mock file already generated, and touch nothing else.

The file is never regenerated for a wrong insight: a new file would reshuffle which members use
which photo, renumber refs and break the posts already imported. Instead, for the listed photos
only, `images[].insight` (and the scene, when the library changed it) takes the photo library's
current entry; members, insights, posts, refs, times, places, views and the seed stay as they
were. A photo whose library outcome is no longer `insights` gets `null`, as the generator would
write it.

This module only edits a loaded document and describes what changed (references, never text);
`mockdata.process patch` runs the importer's checks and writes the file and the report.
"""

from __future__ import annotations

import argparse
from typing import Any

from mockdata.library import KEPT

PATCH_REPORT_NAME = "patch-report.json"
# What became of a photo the patch was asked for.
REPLACED = "replaced"
FILLED = "filled"
EMPTIED = "emptied"
UNCHANGED = "unchanged"
NOT_IN_FILE = "not_in_file"


def parse_ids(text: str) -> frozenset[int]:
    """Placepix ids from `12,40,7`; an argparse type, so a mistake is a usage error."""
    try:
        ids = frozenset(int(part) for part in text.split(",") if part.strip())
    except ValueError:
        message = f"placepix ids are whole numbers separated by commas, not {text!r}"
        raise argparse.ArgumentTypeError(message) from None
    if not ids or min(ids) < 1:
        message = "give at least one placepix id, each 1 or more"
        raise argparse.ArgumentTypeError(message)
    return ids


def evidence_of(body: dict[str, Any] | None) -> dict[str, str | None] | None:
    """Which verse and hadith an insight points to, as `surah:ayah` and `collection:number`."""
    if body is None:
        return None
    verse, hadith = body.get("quran"), body.get("hadith")
    return {
        "quran": f"{verse['surah']}:{verse['ayah']}" if verse else None,
        "hadith": f"{hadith['collection']}:{hadith['number']}" if hadith else None,
    }


def result_of(old: dict[str, Any] | None, new: dict[str, Any] | None, *, scene: bool) -> str:
    if new is None and old is not None:
        return EMPTIED
    if old is None and new is not None:
        return FILLED
    return REPLACED if new != old or scene else UNCHANGED


def patch_images(
    document: dict[str, Any], entries: dict[str, dict[str, Any]], ids: frozenset[int]
) -> list[dict[str, Any]]:
    """
    Put the library's current insight and scene on the listed photos of the document, in place.

    Every id must be in `entries` (the caller refuses the others). A photo the file does not use
    is reported, not added: adding one would change the file's insights.
    """
    images = {image["placepix_id"]: image for image in document["images"]}
    changes: list[dict[str, Any]] = []
    for pid in sorted(ids):
        image, entry = images.get(pid), entries[str(pid)]
        if image is None:
            changes.append({"photo": pid, "result": NOT_IN_FILE, "outcome": entry["outcome"]})
            continue
        new = entry["insight"] if entry["outcome"] == KEPT else None
        scene = image["scene"] != entry["scene"]
        result = result_of(image["insight"], new, scene=scene)
        changes.append(
            {
                "photo": pid,
                "result": result,
                "outcome": entry["outcome"],
                "from": evidence_of(image["insight"]),
                "to": evidence_of(new),
                "scene_changed": scene,
            }
        )
        image["insight"], image["scene"] = new, entry["scene"]
    return changes


def changed(changes: list[dict[str, Any]]) -> list[int]:
    """The photos whose entry in the file is not what it was."""
    return [c["photo"] for c in changes if c["result"] not in {UNCHANGED, NOT_IN_FILE}]
