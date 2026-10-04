"""
Turn the learning path reference into versioned data.

    uv run python -m src.cli.parse_masar [--source FILE] [--out FILE] [--path-version ID]
                                          [--expect-domains N] [--expect-units N] [--check]

Reads `docs/spec/masar.md` (never modified), validates what it found, and writes
`data/masar/<path_version>.json`. With `--check` nothing is written: the command
fails when the file on disk is not what the document produces, which is how a
build notices a document edited without its data. Exits 1 on any problem.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from src.schemas.learning_path import dumps
from src.services.masar_parser import MasarParseError, parse_masar
from src.services.masar_validator import LearningPathError, validate_path

# apps/api/src/cli/parse_masar.py -> the repository root, four levels up.
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SOURCE = REPO_ROOT / "docs" / "spec" / "masar.md"
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "masar"


def _say(line: str) -> None:
    sys.stdout.write(f"{line}\n")


def _recorded_name(source: Path) -> str:
    """Return the name the data records for its source: relative to the repository when inside it."""
    try:
        return source.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return source.name


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the document; return the process exit code."""
    parser = argparse.ArgumentParser(description="Parse the TABSIRA learning path reference.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="the Markdown document")
    parser.add_argument(
        "--out", type=Path, help="the JSON file (default: data/masar/<version>.json)"
    )
    parser.add_argument("--path-version", help="default: tabsira-masar-<version of the document>")
    parser.add_argument("--expect-domains", type=int)
    parser.add_argument("--expect-units", type=int)
    parser.add_argument("--check", action="store_true", help="fail if the JSON is not up to date")
    args = parser.parse_args(argv)

    started = time.perf_counter()
    try:
        text = args.source.read_text(encoding="utf-8")
    except OSError as error:
        sys.stderr.write(f"Cannot read {args.source}: {error.strerror or type(error).__name__}.\n")
        return 1
    try:
        path = parse_masar(
            text, source_name=_recorded_name(args.source), path_version=args.path_version
        )
        validate_path(path, expected_domains=args.expect_domains, expected_units=args.expect_units)
    except (MasarParseError, LearningPathError) as error:
        sys.stderr.write(f"{error}\n")
        return 1

    target = args.out or DEFAULT_OUT_DIR / f"{path.path_version}.json"
    data = dumps(path)
    _say(
        f"learning path {path.path_version}: {path.counts.domains} domains, {path.counts.units} units"
    )
    if args.check:
        current = target.read_text(encoding="utf-8") if target.exists() else None
        if current != data:
            sys.stderr.write(
                f"{target} is not what {args.source.name} produces. Run the command without --check.\n"
            )
            return 1
        _say(f"  {target} is up to date ({time.perf_counter() - started:.2f} s)")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(data, encoding="utf-8")
    _say(
        f"  wrote {target} ({len(data.encode()) / 1024:.0f} KiB, {time.perf_counter() - started:.2f} s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
