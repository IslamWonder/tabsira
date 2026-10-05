"""The file of version 1: typed models and deterministic JSON. References only, no scripture."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1


def stamp(moment: datetime) -> str:
    """A naive UTC time as `2026-10-05T10:00:00Z`; every time in the generator is naive UTC."""
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class _Row(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Scene(_Row):
    labels: list[str]
    ar: str


class Image(_Row):
    placepix_id: int
    url: str
    filename: str
    category: str
    width: int
    height: int
    scene: Scene
    # The pipeline's insight from the photo library (task 23.4), in the importer's shape.
    insight: dict[str, Any] | None = None


class Member(_Row):
    ref: str
    handle: str
    display_name: str
    email: str
    country: str
    city_geoname_id: int
    joined_at: str
    # What the person declared in the profile form: private, as for every member.
    gender: str
    age_range: str
    goals: list[str]
    knowledge_level: str
    religious_background: str
    theme: str
    reduced_motion: str
    sound: bool
    public_full_name: bool


class Feedback(_Row):
    helpful: bool
    reasons: list[str] = []
    at: str


class Insight(_Row):
    ref: str
    member: str
    image: int
    created_at: str
    completed_at: str
    # GeoJSON order: [longitude, latitude].
    point: tuple[float, float]
    feedback: Feedback | None = None


class Post(_Row):
    ref: str
    insight: str
    published_at: str
    reflection: None = None
    visibility: str = "public"
    # Whether the post shows the insight's photo; whether the author wrote a reflection.
    photo: bool = True
    reflect: bool = True


class Sponsor(_Row):
    member: str
    at: str
    reflection: None = None


class MapEntry(_Row):
    insight: str
    published_at: str
    orphaned: bool = False
    sponsor: Sponsor | None = None


class Follow(_Row):
    from_: str = Field(alias="from")
    to: str
    at: str


class Bookmark(_Row):
    post: str
    member: str
    at: str


class Block(_Row):
    from_: str = Field(alias="from")
    to: str
    at: str


class Reaction(_Row):
    post: str
    member: str
    kind: str
    at: str


class Comment(_Row):
    ref: str
    post: str
    member: str
    parent: str | None
    text: None = None
    at: str


class MockFile(_Row):
    version: int = SCHEMA_VERSION
    seed: int
    generated_at: str
    images: list[Image]
    members: list[Member]
    insights: list[Insight]
    posts: list[Post]
    map_entries: list[MapEntry]
    follows: list[Follow]
    blocks: list[Block]
    reactions: list[Reaction]
    bookmarks: list[Bookmark]
    comments: list[Comment]


def dumps(file: MockFile) -> str:
    """Sorted keys, UTF-8 text, no ASCII escapes: the same input is the same bytes."""
    return json.dumps(
        file.model_dump(by_alias=True),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def write(path: Path, file: MockFile) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((dumps(file) + "\n").encode("utf-8"))
