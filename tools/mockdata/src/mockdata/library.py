"""
The two durable libraries of the mock data, beside the file in `../tabsira-data/mock/`.

- `photo-library.json`: every placepix photo the real pipeline has seen, keyed by its id, with
  its outcome and, when it gave one, the insight in the importer's shape. It is the source of
  truth for photo content: the generator builds the mock activity from its photos with an
  insight, and a later run of the photo stage adds new ids and never redoes one it holds.
- `texts-library.json`: the reflections and comment texts accepted for each post, keyed by the
  post and its insight's photo, so writing the file again does not pay for them twice.

Both only grow; each is rewritten whole, beside itself then renamed, after every entry.
Neither holds a verse or a hadith text, nor anything a model wrote that was not accepted.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PHOTOS_NAME = "photo-library.json"
TEXTS_NAME = "texts-library.json"
LIBRARY_VERSION = 1
KEPT = "insights"
# The outcomes a photo keeps in the library; anything else that ends a photo is an error.
OUTCOMES = frozenset({KEPT, "needs_clarification", "no_relevant_evidence", "people", "sensitive"})
ERROR = "error"


def dumps(document: dict[str, Any]) -> str:
    """Sorted keys, UTF-8 text, compact: the same content is the same bytes."""
    return json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def write_atomically(path: Path, text: str) -> None:
    """Write beside the target, then rename: a crash leaves the old file or the new one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.partial")
    partial.write_bytes(text.encode("utf-8"))
    partial.replace(path)


@dataclass
class Library:
    """A JSON document of entries under one key, plus the record of the runs that wrote it."""

    path: Path
    key: str
    data: dict[str, Any]
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @classmethod
    def load(cls, path: Path, key: str) -> Library:
        if path.exists():
            return cls(path, key, json.loads(path.read_text(encoding="utf-8")))
        return cls(path, key, {"version": LIBRARY_VERSION, key: {}, "runs": []})

    @property
    def entries(self) -> dict[str, dict[str, Any]]:
        entries: dict[str, dict[str, Any]] = self.data[self.key]
        return entries

    @property
    def runs(self) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = self.data["runs"]
        return runs

    async def put(self, name: str, entry: dict[str, Any]) -> None:
        """Add or replace one entry and write the library at once."""
        async with self._lock:
            self.entries[name] = entry
            write_atomically(self.path, dumps(self.data) + "\n")

    async def save(self) -> None:
        async with self._lock:
            write_atomically(self.path, dumps(self.data) + "\n")


def photos(path: Path) -> Library:
    return Library.load(path, "photos")


def texts(path: Path) -> Library:
    return Library.load(path, "posts")


def kept_photos(library: Library) -> dict[int, dict[str, Any]]:
    """The photos with an insight, by placepix id, in id order."""
    found = {int(pid): entry for pid, entry in library.entries.items() if entry["outcome"] == KEPT}
    return dict(sorted(found.items()))


def outcome_of(outcome: str) -> str:
    """The library's outcome for a pipeline outcome that ended the photo."""
    return outcome if outcome in OUTCOMES else ERROR


def text_key(post: str, placepix_id: int) -> str:
    return f"{post}:{placepix_id}"
