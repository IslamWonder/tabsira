"""The placepix catalogue: fetched politely once, cached, filtered for people."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "https://placepix.net"
PHOTO_URL = BASE_URL + "/id/{id}/1080/1080"
MAX_KEY_LENGTH = 64  # photo_key column of the insights table

KEEP_CATEGORIES = frozenset(
    {
        "animal",
        "bird",
        "cat",
        "dog",
        "flower",
        "food",
        "nature",
        "city",
        "travel",
        "interior",
        "education",
        "transportation",
    }
)

# Any filename word that names a person, a face or a body drops the photo, so no child
# or face is ever shown (decision 63, plan 22.2).
HUMAN_WORDS = frozenset(
    {
        "person", "people", "man", "men", "woman", "women", "girl", "girls", "boy", "boys",
        "child", "children", "kid", "kids", "baby", "face", "faces", "portrait", "selfie",
        "family", "crowd", "hand", "hands", "body", "model", "student", "students", "teacher",
        "lady", "guy", "couple", "friends", "worker", "workers", "human", "toddler", "bride",
        "groom", "player", "players", "pedestrian", "pedestrians", "tourist", "tourists",
        "customer", "customers", "doctor", "nurse", "dancer", "runner", "mother", "father",
        "smile", "smiling", "hair", "eye", "eyes", "foot", "feet", "legs", "arm", "arms",
    }
)  # fmt: skip
ANIMAL_CATEGORIES = frozenset({"animal", "bird", "cat", "dog"})
ANIMAL_WORDS = frozenset({"cat", "dog", "animal", "puppy", "kitten", "bird"})

_WORD = re.compile(r"[A-Za-z][a-z]*|[A-Z]+(?![a-z])")


@dataclass(frozen=True)
class Photo:
    id: int
    filename: str
    category: str
    width: int
    height: int

    @property
    def url(self) -> str:
        return PHOTO_URL.format(id=self.id)


def words(filename: str) -> list[str]:
    """Lower-case words of a filename, split on separators, digits and camel case."""
    stem = filename.rsplit(".", 1)[0]
    return [w.lower() for w in _WORD.findall(stem)]


def names_a_human(photo: Photo) -> bool:
    found = set(words(photo.filename))
    # A singular or plural form is the same word for this check.
    found |= {w.removesuffix("s") for w in found}
    hits = found & HUMAN_WORDS
    if hits == {"portrait"} and (found & ANIMAL_WORDS or photo.category in ANIMAL_CATEGORIES):
        return False
    return bool(hits)


def keep(photo: Photo) -> bool:
    return photo.category in KEEP_CATEGORIES and not names_a_human(photo)


def filter_photos(photos: list[Photo]) -> list[Photo]:
    return sorted((p for p in photos if keep(p)), key=lambda p: p.id)


def fetch_catalogue(
    client: httpx.Client,
    delay: float = 0.15,
    sleep: Callable[[float], None] = time.sleep,
    max_gap: int = 10,
) -> list[Photo]:
    """Fetch every photo, one request at a time. Stops after `max_gap` ids in a row are missing."""
    info = client.get(f"{BASE_URL}/api/categories")
    info.raise_for_status()
    expected = sum(int(c["count"]) for c in info.json()["detailed"])
    photos: list[Photo] = []
    gap = 0
    n = 0
    while len(photos) < expected and gap < max_gap:
        n += 1
        sleep(delay)
        response = client.get(f"{BASE_URL}/api/info/id/{n}")
        if response.status_code != 200:
            gap += 1
            continue
        gap = 0
        data = response.json()
        photos.append(
            Photo(
                id=int(data["id"]),
                filename=str(data["filename"]),
                category=str(data["category"]),
                width=int(data["width"]),
                height=int(data["height"]),
            )
        )
    return photos


def save(path: Path, photos: list[Photo]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = [asdict(p) for p in photos]
    path.write_text(
        json.dumps(rows, sort_keys=True, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def load(path: Path) -> list[Photo]:
    return [Photo(**row) for row in json.loads(path.read_text(encoding="utf-8"))]


def get_catalogue(cache: Path, refresh: bool, fetch: Callable[[], list[Photo]]) -> list[Photo]:
    """Return the cached catalogue, or fetch it and cache it for the next run."""
    if refresh or not cache.exists():
        save(cache, fetch())
    return load(cache)
