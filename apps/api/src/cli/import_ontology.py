"""
Import the world ontology workbook.

    uv run python -m src.cli.import_ontology [--source FILE] [--json FILE] [--expected-count N]
                                              [--validate-only] [--no-json] [--no-db]

Reads and validates `data/world-ontology.xlsx` (it is never modified), writes the
generated `data/ontology/world-ontology.json`, and loads `corpus.ontology_entities`
in one transaction. Re-running with the same file changes nothing but the import
time. Exits 0 on success and 1 when the workbook is broken, naming each problem,
or when the database cannot be loaded.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import ConfigError
from src.database import dispose_engine, get_sessionmaker
from src.services.ontology_import import (
    EXPECTED_COUNT,
    OntologyImportError,
    ParsedOntology,
    export_json,
    load_ontology,
    read_workbook,
)

# apps/api/src/cli/import_ontology.py -> the repository root, four levels up.
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SOURCE = REPO_ROOT / "data" / "world-ontology.xlsx"
DEFAULT_JSON = REPO_ROOT / "data" / "ontology" / "world-ontology.json"


@dataclass(frozen=True, slots=True)
class Options:
    source: Path
    json_path: Path | None
    expected_count: int
    load_database: bool


def _say(line: str) -> None:
    sys.stdout.write(f"{line}\n")


def _parse_arguments(argv: Sequence[str] | None) -> Options:
    parser = argparse.ArgumentParser(description="Import the TABSIRA world ontology.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="the .xlsx workbook")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON, help="where to write the JSON")
    parser.add_argument("--expected-count", type=int, default=EXPECTED_COUNT)
    parser.add_argument("--validate-only", action="store_true", help="validate, write nothing")
    parser.add_argument("--no-json", action="store_true", help="do not write the JSON file")
    parser.add_argument("--no-db", action="store_true", help="do not touch the database")
    args = parser.parse_args(argv)
    return Options(
        source=args.source,
        json_path=None if args.no_json or args.validate_only else args.json,
        expected_count=args.expected_count,
        load_database=not (args.no_db or args.validate_only),
    )


def _report_parse(parsed: ParsedOntology, seconds: float) -> None:
    _say(f"ontology: {parsed.source_name}, sheet «{parsed.sheet}»")
    _say(f"  sha256 {parsed.source_sha256}")
    _say(f"  valid: {len(parsed.rows)} entities, {len(parsed.domains)} domains ({seconds:.2f} s)")
    for text, count in parsed.constraint_counts.items():
        _say(f"  constraint {count:>4}  {text}")
    for warning in parsed.warnings:
        sys.stderr.write(f"  warning: {warning}\n")


def _write_json(parsed: ParsedOntology, path: Path) -> None:
    started = time.perf_counter()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = export_json(parsed)
    # LF on every system: the file is tracked, and Windows would write CRLF.
    path.write_text(text, encoding="utf-8", newline="\n")
    seconds = time.perf_counter() - started
    _say(f"  json: wrote {path} ({len(text.encode()) / 1024:.0f} KiB, {seconds:.2f} s)")


async def _load(parsed: ParsedOntology, session_factory: async_sessionmaker[AsyncSession]) -> None:
    started = time.perf_counter()
    async with session_factory() as session, session.begin():
        result = await load_ontology(session, parsed)
    seconds = time.perf_counter() - started
    _say(
        f"  database: {result.inserted} inserted, {result.updated} updated, "
        f"{result.removed} removed ({seconds:.2f} s)"
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
        parsed = read_workbook(options.source, expected_count=options.expected_count)
    except OntologyImportError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    _report_parse(parsed, time.perf_counter() - started)
    if options.json_path is not None:
        _write_json(parsed, options.json_path)
    if options.load_database:
        try:
            factory = session_factory or get_sessionmaker()
        except ConfigError as error:
            sys.stderr.write(f"{error}\n")
            return 1
        try:
            await _load(parsed, factory)
        except (SQLAlchemyError, OSError) as error:
            sys.stderr.write(
                f"Cannot load the ontology into the database ({type(error).__name__}). "
                "Is it migrated? Run `make migrate`.\n"
            )
            return 1
        finally:
            if session_factory is None:
                await dispose_engine()
    _say(f"  done in {time.perf_counter() - started:.2f} s")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Import the ontology; return the process exit code."""
    return asyncio.run(execute(_parse_arguments(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
