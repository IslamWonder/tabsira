"""
Import a learning path version into the database.

    uv run python -m src.cli.import_masar [--source FILE] [--activate | --no-activate]
                                           [--replace] [--expect-domains N] [--expect-units N]

Validates `data/masar/<path_version>.json` and loads it into `app.learning_*` in one
transaction. The same file again changes nothing. A first version becomes the active
one; a later version waits unless `--activate` is given. A published version is
replaced only with `--replace`. A new monthly release is a new file of the same shape,
imported the same way: nothing in the code changes. Exits 1 on any problem.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import ConfigError
from src.database import dispose_engine, get_sessionmaker
from src.services.masar_import import PathVersionConflictError, import_path
from src.services.masar_validator import LearningPathError, load_path, validate_path

# apps/api/src/cli/import_masar.py -> the repository root, four levels up.
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SOURCE = REPO_ROOT / "data" / "masar" / "tabsira-masar-1.0.json"


@dataclass(frozen=True, slots=True)
class Options:
    source: Path
    activate: bool | None
    replace: bool
    expect_domains: int | None
    expect_units: int | None


def _say(line: str) -> None:
    sys.stdout.write(f"{line}\n")


def _parse_arguments(argv: Sequence[str] | None) -> Options:
    parser = argparse.ArgumentParser(description="Import a TABSIRA learning path version.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="the path version JSON")
    switch = parser.add_mutually_exclusive_group()
    switch.add_argument("--activate", dest="activate", action="store_true", default=None)
    switch.add_argument("--no-activate", dest="activate", action="store_false")
    parser.add_argument("--replace", action="store_true", help="replace a published version")
    parser.add_argument("--expect-domains", type=int)
    parser.add_argument("--expect-units", type=int)
    args = parser.parse_args(argv)
    return Options(
        source=args.source,
        activate=args.activate,
        replace=args.replace,
        expect_domains=args.expect_domains,
        expect_units=args.expect_units,
    )


async def execute(
    options: Options, session_factory: async_sessionmaker[AsyncSession] | None = None
) -> int:
    """
    Run the import described by `options`; return the exit code.

    Without a `session_factory` the application's own engine is used and closed
    when the import ends.
    """
    started = time.perf_counter()
    try:
        data = options.source.read_bytes()
    except OSError as error:
        reason = error.strerror or type(error).__name__
        sys.stderr.write(f"Cannot read {options.source}: {reason}.\n")
        return 1
    try:
        path = load_path(data.decode("utf-8", errors="replace"))
        validate_path(
            path, expected_domains=options.expect_domains, expected_units=options.expect_units
        )
    except LearningPathError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    _say(
        f"learning path {path.path_version}: {path.counts.domains} domains, {path.counts.units} units"
    )
    _say(f"  valid ({time.perf_counter() - started:.2f} s)")

    try:
        factory = session_factory or get_sessionmaker()
    except ConfigError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    try:
        async with factory() as session, session.begin():
            result = await import_path(
                session,
                path,
                source_file=options.source.name,
                source_sha256=hashlib.sha256(data).hexdigest(),
                activate=options.activate,
                replace=options.replace,
            )
    except PathVersionConflictError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    except (SQLAlchemyError, OSError) as error:
        sys.stderr.write(
            f"Cannot load the learning path into the database ({type(error).__name__}). "
            "Is it migrated? Run `make migrate`.\n"
        )
        return 1
    finally:
        if session_factory is None:
            await dispose_engine()
    _say(
        f"  database: {result.status.value}, {result.domains} domains, {result.units} units, "
        f"{'active' if result.active else 'not active'} ({time.perf_counter() - started:.2f} s)"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Import the learning path; return the process exit code."""
    return asyncio.run(execute(_parse_arguments(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
