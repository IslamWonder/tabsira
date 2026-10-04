"""
Validate a learning path file before it is imported.

`LearningPathFile` already says what each field is. This module checks what must hold
across the whole file, and fails with `LearningPathError` listing every problem:

- the counts the file declares are the counts it holds (and, when the caller says what
  a release must hold, those counts: version 1.0 has 16 domains and 96 units);
- ids and orders are unique and run without gaps, a unit's id begins with its domain's;
- every prerequisite is a unit of the file, none points at itself, and there is no
  cycle (a prerequisite is knowledge to prepare, so a cycle could never be prepared);
- every depth a unit lists is a depth the file defines;
- every coverage rule points at units that exist;
- an evidence reference is a pointer, not a quotation: short, without the marks or
  the ornate brackets of Quranic text.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from src.schemas.learning_path import LearningPathFile

MAX_PROBLEMS_SHOWN = 25
# A pointer such as «الإسراء 36» is short; a longer «reference» is probably a quotation.
MAX_REFERENCE_LENGTH = 120
# The marks of Quranic text (U+06D6 to U+06ED) and its ornate brackets (U+FD3E, U+FD3F).
_QURANIC_MARKS = re.compile(f"[{chr(0x06D6)}-{chr(0x06ED)}{chr(0xFD3E)}{chr(0xFD3F)}]")


class LearningPathError(Exception):
    """The learning path file is not valid; `problems` lists what is wrong, one line each."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        shown = self.problems[:MAX_PROBLEMS_SHOWN]
        lines = [f"The learning path file is not valid ({len(self.problems)} problem(s)):"]
        lines.extend(f"  - {problem}" for problem in shown)
        if len(self.problems) > len(shown):
            lines.append(f"  - ... and {len(self.problems) - len(shown)} more")
        super().__init__("\n".join(lines))


def load_path(text: str) -> LearningPathFile:
    """Read the JSON text of a learning path file into its typed form, or say what is malformed."""
    try:
        return LearningPathFile.model_validate(json.loads(text))
    except json.JSONDecodeError as error:
        raise LearningPathError([f"Not JSON: {error.msg} at line {error.lineno}."]) from None
    except ValidationError as error:
        problems = [
            f"{'.'.join(map(str, item['loc'])) or 'file'}: {item['msg']}" for item in error.errors()
        ]
        raise LearningPathError(problems) from None


def _duplicates(values: Sequence[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


def _check_order(label: str, orders: list[int]) -> list[str]:
    return (
        []
        if sorted(orders) == list(range(1, len(orders) + 1))
        else [f"{label} do not run from 1 without a gap: {sorted(orders)}."]
    )


def _cycle(prerequisites: dict[str, list[str]]) -> list[str] | None:
    """Return one cycle of the prerequisite graph as a list of ids, or None when there is none."""
    state: dict[str, int] = {}  # 1 on the current path, 2 finished
    path: list[str] = []

    def visit(unit: str) -> list[str] | None:
        state[unit] = 1
        path.append(unit)
        for before in prerequisites.get(unit, []):
            if state.get(before) == 1:
                return [*path[path.index(before) :], before]
            if before not in state and (found := visit(before)) is not None:
                return found
        state[unit] = 2
        path.pop()
        return None

    for unit in prerequisites:
        if unit not in state and (found := visit(unit)) is not None:
            return found
    return None


def _check_counts(
    path: LearningPathFile, expected_domains: int | None, expected_units: int | None
) -> list[str]:
    problems = []
    if path.counts.domains != len(path.domains):
        problems.append(
            f"The file declares {path.counts.domains} domains and holds {len(path.domains)}."
        )
    if path.counts.units != len(path.units):
        problems.append(f"The file declares {path.counts.units} units and holds {len(path.units)}.")
    if expected_domains is not None and len(path.domains) != expected_domains:
        problems.append(
            f"{expected_domains} domains were expected, the file holds {len(path.domains)}."
        )
    if expected_units is not None and len(path.units) != expected_units:
        problems.append(f"{expected_units} units were expected, the file holds {len(path.units)}.")
    return problems


def _check_structure(path: LearningPathFile) -> list[str]:
    problems = [
        f"Depth {code} is defined more than once."
        for code in _duplicates([d.code for d in path.depths])
    ]
    problems += [
        f"Domain {d} appears more than once." for d in _duplicates([d.id for d in path.domains])
    ]
    problems += _check_order("The domain orders", [d.order for d in path.domains])
    problems += [
        f"Unit {u} appears more than once." for u in _duplicates([u.id for u in path.units])
    ]
    domains = {domain.id for domain in path.domains}
    codes = {depth.code for depth in path.depths}
    by_domain: dict[str, list[int]] = {domain: [] for domain in domains}
    for unit in path.units:
        if unit.domain not in domains:
            problems.append(
                f"Unit {unit.id} belongs to {unit.domain}, which is not a domain of the file."
            )
            continue
        by_domain[unit.domain].append(unit.order)
        if not unit.id.startswith(f"{unit.domain}_"):
            problems.append(f"Unit {unit.id} is not named after its domain {unit.domain}.")
        if unit.id != f"{unit.domain}_{unit.order:02d}":
            problems.append(f"Unit {unit.id} is at order {unit.order}, which its id does not say.")
        if missing := sorted(set(unit.depths) - codes):
            problems.append(
                f"Unit {unit.id} lists depths the file does not define: {', '.join(missing)}."
            )
        if _duplicates(unit.depths):
            problems.append(f"Unit {unit.id} lists a depth twice.")
    for domain, orders in sorted(by_domain.items()):
        if not orders:
            problems.append(f"Domain {domain} has no unit.")
        else:
            problems += _check_order(f"The unit orders of {domain}", orders)
    return problems


def _check_prerequisites(path: LearningPathFile) -> list[str]:
    known = {unit.id for unit in path.units}
    problems = []
    graph: dict[str, list[str]] = {}
    for unit in path.units:
        graph[unit.id] = [
            before for before in unit.prerequisites if before in known and before != unit.id
        ]
        for before in unit.prerequisites:
            if before == unit.id:
                problems.append(f"Unit {unit.id} is its own prerequisite.")
            elif before not in known:
                problems.append(
                    f"Unit {unit.id} has the prerequisite {before}, which is not a unit of the file."
                )
        if _duplicates(unit.prerequisites):
            problems.append(f"Unit {unit.id} lists a prerequisite twice.")
    if (cycle := _cycle(graph)) is not None:
        problems.append(f"The prerequisites form a cycle: {' -> '.join(cycle)}.")
    return problems


def _check_references(path: LearningPathFile) -> list[str]:
    problems: list[str] = []
    for unit in path.units:
        problems.extend(
            f"Unit {unit.id} has a reference that is not a pointer: «{ref[:40]}...»."
            for ref in unit.evidence_refs
            if len(ref) > MAX_REFERENCE_LENGTH or _QURANIC_MARKS.search(ref)
        )
        if _duplicates(unit.source_anchors):
            problems.append(f"Unit {unit.id} lists a source anchor twice.")
    known = {unit.id for unit in path.units}
    problems.extend(
        f"The coverage rule «{rule.asset}» names units that do not exist: {', '.join(unknown)}."
        for rule in path.coverage
        if (unknown := sorted(set(rule.units) - known))
    )
    return problems


def validate_path(
    path: LearningPathFile,
    *,
    expected_domains: int | None = None,
    expected_units: int | None = None,
) -> None:
    """Raise `LearningPathError` with every problem found in `path`; return when there is none."""
    problems = [
        *_check_counts(path, expected_domains, expected_units),
        *_check_structure(path),
        *_check_prerequisites(path),
        *_check_references(path),
    ]
    if problems:
        raise LearningPathError(problems)


def read_path(
    file: Path, *, expected_domains: int | None = None, expected_units: int | None = None
) -> LearningPathFile:
    """Read, type-check and validate the learning path file at `file`."""
    try:
        text = file.read_text(encoding="utf-8")
    except OSError as error:
        raise LearningPathError(
            [f"Cannot read {file}: {error.strerror or type(error).__name__}."]
        ) from None
    path = load_path(text)
    validate_path(path, expected_domains=expected_domains, expected_units=expected_units)
    return path
