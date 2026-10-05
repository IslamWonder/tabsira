"""
Command line: `python -m mockdata.cli` writes the mock file of version 1.

The photos are the photo library's that gave an insight (`make mock-photos`), with that
insight; the members, their places and the follows depend on the seed alone, so they stay the
same when only the library grows.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import psycopg

from mockdata import catalogue, library, places
from mockdata.activity import Knobs, make_activity
from mockdata.catalogue import Photo
from mockdata.members import make_members
from mockdata.output import Image, MockFile, stamp, write
from mockdata.places import City, Connection, Gazetteer
from mockdata.scenes import describe

# The repository root is four levels above this file; the data folder sits beside the checkout.
DATA_DIR = Path(__file__).resolve().parents[5] / "tabsira-data" / "mock"
REPO_ROOT = Path(__file__).resolve().parents[4]
OUT_NAME = "tabsira-mock-v1.json"


def database_url(env_file: Path) -> str:
    """DATABASE_URL from the environment or the env file, in psycopg's form."""
    url = os.environ.get("DATABASE_URL", "")
    if not url and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip().strip("\"'")
    if not url:
        message = f"DATABASE_URL is not set and {env_file} does not define it"
        raise SystemExit(message)
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def connect_read_only(url: str) -> Connection:
    conn = psycopg.connect(url, autocommit=True)
    conn.read_only = True
    return conn


def fetch_photos() -> list[Photo]:
    with httpx.Client(timeout=30.0) as client:
        return catalogue.fetch_catalogue(client)


def library_photos(path: Path) -> tuple[list[Photo], dict[int, dict[str, Any]]]:
    """The photos of the photo library that gave an insight, and their library entries."""
    if not path.exists():
        message = f"{path} does not exist: run make mock-photos first"
        raise SystemExit(message)
    kept = library.kept_photos(library.photos(path))
    photos = [
        Photo(pid, entry["filename"], entry["category"], entry["width"], entry["height"])
        for pid, entry in kept.items()
    ]
    return photos, kept


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mockdata", description="Generate the mock members file.")
    env = os.environ.get
    p.add_argument("--seed", type=int, default=int(env("MOCK_SEED", "42")))
    p.add_argument("--members", type=int, default=int(env("MOCK_MEMBERS", "1000")))
    p.add_argument("--now", help="fixed UTC time, 2026-10-05T10:00:00Z; default: current time")
    p.add_argument("--out", type=Path, default=DATA_DIR / OUT_NAME)
    p.add_argument("--photos-from", type=Path, default=DATA_DIR / library.PHOTOS_NAME)
    p.add_argument("--places-cache", type=Path, default=DATA_DIR / "places-cache.json")
    p.add_argument("--refresh-places", action="store_true")
    p.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")
    defaults = Knobs()
    for name, value in vars(defaults).items():
        p.add_argument(f"--{name.replace('_', '-')}", type=int, default=value)
    return p


def resolve_now(text: str | None) -> datetime:
    if text is None:
        return datetime.now(UTC).replace(microsecond=0, tzinfo=None)
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")


def load_gazetteer(
    cache: Path, refresh: bool, open_connection: Callable[[], Connection]
) -> Gazetteer:
    if refresh or not cache.exists():
        places.save(cache, places.fetch_gazetteer(open_connection()))
    return places.load(cache)


def build(
    args: argparse.Namespace,
    photos: list[Photo],
    gazetteer: Gazetteer,
    now: datetime,
    content: dict[int, dict[str, Any]] | None = None,
) -> MockFile:
    cities: dict[str, list[City]] = {}
    for city in gazetteer.cities:
        cities.setdefault(city.country, []).append(city)
    members = make_members(args.seed, args.members, now, cities)
    knobs = Knobs(**{k: getattr(args, k) for k in vars(Knobs())})
    activity = make_activity(args.seed, members, photos, gazetteer, knobs, now)
    used = {i.image for i in activity.insights}
    images = [
        Image(
            placepix_id=p.id,
            url=p.url,
            filename=p.filename,
            category=p.category,
            width=p.width,
            height=p.height,
            scene=describe(p.filename, p.category),
            insight=(content or {}).get(p.id, {}).get("insight"),
        )
        for p in photos
        if p.id in used
    ]
    return MockFile(
        seed=args.seed,
        generated_at=stamp(now),
        images=images,
        members=members,
        insights=activity.insights,
        posts=activity.posts,
        map_entries=activity.map_entries,
        follows=activity.follows,
        reactions=activity.reactions,
        comments=activity.comments,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    connect: Callable[[str], Connection] = connect_read_only,
) -> int:
    args = parser().parse_args(argv)
    now = resolve_now(args.now)
    photos, content = library_photos(args.photos_from)
    gazetteer = load_gazetteer(
        args.places_cache,
        args.refresh_places,
        lambda: connect(database_url(args.env_file)),
    )
    file = build(args, photos, gazetteer, now, content)
    write(args.out, file)
    print(
        f"{args.out}: {len(file.members)} members, {len(file.images)} images, "
        f"{len(file.insights)} insights, {len(file.posts)} posts, "
        f"{len(file.map_entries)} map entries, {len(file.follows)} follows, "
        f"{len(file.reactions)} reactions, {len(file.comments)} comments"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
