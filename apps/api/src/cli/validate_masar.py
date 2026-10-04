"""
Validate a learning path file.

    uv run python -m src.cli.validate_masar FILE [--expect-domains N] [--expect-units N]

Checks the shape of the file and everything that must hold across it: the counts, ids
and orders, the prerequisites (they exist, and there is no cycle), the depths, the
coverage rules and the evidence pointers. Exits 0 when the file is valid and 1 when
it is not, listing every problem.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from src.services.masar_validator import LearningPathError, read_path


def main(argv: Sequence[str] | None = None) -> int:
    """Validate the file named on the command line; return the process exit code."""
    parser = argparse.ArgumentParser(description="Validate a TABSIRA learning path file.")
    parser.add_argument("file", type=Path)
    parser.add_argument("--expect-domains", type=int)
    parser.add_argument("--expect-units", type=int)
    args = parser.parse_args(argv)

    try:
        path = read_path(
            args.file, expected_domains=args.expect_domains, expected_units=args.expect_units
        )
    except LearningPathError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    sys.stdout.write(
        f"valid: {path.path_version}, {path.counts.domains} domains, {path.counts.units} units, "
        f"{len(path.depths)} depths, {len(path.coverage)} coverage rules\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
