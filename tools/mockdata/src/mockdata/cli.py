"""Command line: `python -m mockdata.cli` writes the mock file of version 1."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psycopg

from mockdata import catalogue, places
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


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mockdata", description="Generate the mock members file.")
    env = os.environ.get
    p.add_argument("--seed", type=int, default=int(env("MOCK_SEED", "42")))
    p.add_argument("--members", type=int, default=int(env("MOCK_MEMBERS", "1000")))
    p.add_argument("--now", help="fixed UTC time, 2026-10-05T10:00:00Z; default: current time")
    p.add_argument("--out", type=Path, default=DATA_DIR / OUT_NAME)
    p.add_argument("--catalogue", type=Path, default=DATA_DIR / "placepix-catalogue.json")
    p.add_argument("--places-cache", type=Path, default=DATA_DIR / "places-cache.json")
    p.add_argument("--refresh-catalogue", action="store_true")
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
    args: argparse.Namespace, photos: list[Photo], gazetteer: Gazetteer, now: datetime
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
    fetch: Callable[[], list[Photo]] = fetch_photos,
    connect: Callable[[str], Connection] = connect_read_only,
) -> int:
    args = parser().parse_args(argv)
    now = resolve_now(args.now)
    photos = catalogue.filter_photos(
        catalogue.get_catalogue(args.catalogue, args.refresh_catalogue, fetch)
    )
    gazetteer = load_gazetteer(
        args.places_cache,
        args.refresh_places,
        lambda: connect(database_url(args.env_file)),
    )
    file = build(args, photos, gazetteer, now)
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
