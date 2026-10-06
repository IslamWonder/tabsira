"""
Parse the learning path reference (`docs/spec/masar.md`) into versioned data.

`parse_masar` reads the Markdown and returns a `LearningPathFile`, the shape the
importer and the validator read. It takes only what the document states: the depths
(section 3.2), the domains (section 4), the units with their objective,
prerequisites and anchor references (section 5), the coverage rules (section 6) and
the search vocabulary that section 7 gives for two units. What the document does not
state is not invented; `docs/LEARNING_PATH.md` records how each gap is handled.

Evidence references are pointers (a surah and a verse number, a hadith collection
and number), never the text of a verse or a hadith. Their anchors (`Q:17:36`,
`H:muslim:8a`) are read from the links of the document, and from a plain mention
of a reference that a link elsewhere in the document spells out.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import ValidationError

from src.schemas.learning_path import LearningPathFile

# Arabic month names as the document writes a date: «1 أكتوبر 2026».
MONTHS = {
    "يناير": 1,
    "فبراير": 2,
    "مارس": 3,
    "أبريل": 4,
    "مايو": 5,
    "يونيو": 6,
    "يوليو": 7,
    "أغسطس": 8,
    "سبتمبر": 9,
    "أكتوبر": 10,
    "نوفمبر": 11,
    "ديسمبر": 12,
}

# quran.com addresses a surah by number, except for one link of version 1.0 that
# uses its slug; any other slug has to be added here with its number, on purpose.
SURAH_NUMBER_BY_SLUG = {"al-baqarah": 2}

# Section 7 says, for two units, which Arabic words a unit record holds to match a
# scene. The words are quoted in running text, so they are held here and checked
# against the document: if the text no longer says them, the parse fails.
SECTION_7_VOCABULARY = {
    "T08_03": ("التثبت", "خبر", "نقل", "تحقق"),
    "T12_02": ("إنبات", "غرس الإنسان", "الانتفاع بالغرس"),
}

# The title is stripped in `_sections`: `\s+(.*?)\s*$` backtracks in quadratic time on spaces.
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_UNIT_ID = re.compile(r"T[0-9]{2}_[0-9]{2}")
_ID_OR_RANGE = re.compile(r"`(T[0-9]{2}(?:_[0-9]{2})?)`(?:\s*إلى\s*`(T[0-9]{2}(?:_[0-9]{2})?)`)?")
_QURAN = re.compile(r"^https?://quran\.com/(?P<surah>[^/]+)(?:/(?P<verses>[0-9]+(?:-[0-9]+)?))?/?$")
_SUNNAH = re.compile(r"^https?://sunnah\.com/(?P<collection>[a-z]+):(?P<number>[0-9]+[a-z]?)$")
_STATED_COUNTS = re.compile(r"(?<![0-9])([0-9]+) مجالًا و([0-9]+) وحدة")


class MasarParseError(Exception):
    """The document does not have the structure the parser reads; `problems` says where."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        lines = [f"masar.md cannot be parsed ({len(self.problems)} problem(s)):"]
        lines.extend(f"  - {problem}" for problem in self.problems)
        super().__init__("\n".join(lines))


@dataclass(frozen=True, slots=True)
class _Section:
    level: int
    title: str
    body: tuple[str, ...]


def _sections(lines: list[str]) -> list[_Section]:
    """Split the document at its headings; a section's body runs to the next heading."""
    heads = [
        (index, len(match.group(1)), match.group(2).rstrip())
        for index, line in enumerate(lines)
        if (match := _HEADING.match(line))
    ]
    ends = [index for index, _, _ in heads[1:]] + [len(lines)]
    return [
        _Section(level, title, tuple(lines[index + 1 : end]))
        for (index, level, title), end in zip(heads, ends, strict=True)
    ]


def _table(section: _Section) -> list[list[str]]:
    """Return the data rows of the table of `section`, cells trimmed; the header and the rule are left out."""
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in section.body
        if line.lstrip().startswith("|")
    ]
    return [row for row in rows[1:] if not all(set(cell) <= set("-: ") for cell in row)]


def _plain(cell: str) -> str:
    """Return a cell as plain text: links become their text, code marks and extra spaces go."""
    return " ".join(_LINK.sub(r"\1", cell).replace("`", "").split())


class _Reader:
    """The sections of one document, and the problems found while reading them."""

    def __init__(self, text: str) -> None:
        self.lines = text.splitlines()
        self.sections = _sections(self.lines)
        self.problems: list[str] = []

    def section(self, phrase: str) -> _Section:
        found = next((section for section in self.sections if phrase in section.title), None)
        if found is None:
            self.problems.append(f"No heading contains «{phrase}».")
            return _Section(0, "", ())
        return found

    def meta(self, key: str) -> str | None:
        pattern = re.compile(rf"^\*\*{re.escape(key)}:\*\*\s*(.+?)\s*$")
        value = next((m.group(1) for line in self.lines if (m := pattern.match(line))), None)
        if value is None:
            self.problems.append(f"The document gives no «{key}».")
        return value

    # ─── The header ───

    def released_on(self) -> str | None:
        text = self.meta("التاريخ")
        parts = (text or "").split()
        if text is None:
            return None
        if len(parts) == 3 and parts[0].isdigit() and parts[1] in MONTHS and parts[2].isdigit():
            return date(int(parts[2]), MONTHS[parts[1]], int(parts[0])).isoformat()
        self.problems.append(f"The date «{text}» is not of the form «1 أكتوبر 2026».")
        return None

    # ─── Depths, domains, units ───

    def depths(self) -> list[dict[str, str]]:
        depths = []
        for row in _table(self.section("ستة أعماق")):
            if len(row) < 4 or not re.fullmatch(r"L[0-9]", _plain(row[0])):
                self.problems.append(
                    f"A depth row is not «code | name | ability | example»: {row}."
                )
                continue
            code, name, ability, example = (_plain(cell) for cell in row[:4])
            depths.append({"code": code, "name": name, "ability": ability, "example": example})
        return depths

    def domains(self) -> tuple[list[dict[str, Any]], dict[str, _Section]]:
        """Return the domains of the map and, for each, the section that holds its units."""
        sections = {
            match.group(1): (match.group(2), section)
            for section in self.sections
            if (match := re.fullmatch(r"(T[0-9]{2})\s+(\S.*)", section.title))
        }
        domains: list[dict[str, Any]] = []
        for order, row in enumerate(_table(self.section("خريطة المجالات")), start=1):
            domain_id, name, function, concepts = (_plain(cell) for cell in row[:4])
            heading = sections.get(domain_id)
            if heading is None:
                self.problems.append(
                    f"The domain {domain_id} is in the map but has no section of units."
                )
                continue
            if heading[0] != name:
                self.problems.append(
                    f"The domain {domain_id} is «{name}» in the map and «{heading[0]}» in its section."
                )
            goal = next(
                (
                    _plain(line.split(":**", 1)[1])
                    for line in heading[1].body
                    if line.startswith("**الهدف:**")
                ),
                None,
            )
            if not goal:
                self.problems.append(f"The section of {domain_id} has no «الهدف» line.")
            domains.append(
                {
                    "id": domain_id,
                    "order": order,
                    "title": name,
                    "function": function,
                    "goal": goal or "",
                    "concepts": [c.strip() for c in concepts.split("،") if c.strip()],
                }
            )
        mapped = {domain["id"] for domain in domains}
        for domain_id in sections.keys() - mapped:
            self.problems.append(f"The section of {domain_id} has no row in the map of domains.")
        return domains, {domain_id: sections[domain_id][1] for domain_id in mapped}

    def units(
        self, domains: list[dict[str, Any]], sections: dict[str, _Section], depth_codes: list[str]
    ) -> list[dict[str, Any]]:
        rows = {domain["id"]: _table(sections[domain["id"]]) for domain in domains}
        labels = self._reference_anchors(
            [row for domain_rows in rows.values() for row in domain_rows]
        )
        vocabulary = self.vocabulary()
        units = []
        for domain in domains:
            for order, row in enumerate(rows[domain["id"]], start=1):
                if len(row) < 4:
                    self.problems.append(
                        f"A unit row of {domain['id']} has {len(row)} cells, 4 are expected."
                    )
                    continue
                unit_id = _plain(row[0])
                if unit_id != f"{domain['id']}_{order:02d}":
                    self.problems.append(
                        f"The unit {unit_id} stands at place {order} of {domain['id']}: ids must run in order."
                    )
                refs = _split_references(row[3])
                units.append(
                    {
                        "id": unit_id,
                        "domain": domain["id"],
                        "order": order,
                        "title": _plain(row[1]),
                        "objectives": [_plain(row[1])],
                        "prerequisites": self._prerequisites(row[2], unit_id),
                        "depths": depth_codes,
                        "concepts": vocabulary.get(unit_id, []),
                        "evidence_refs": refs,
                        "source_anchors": _anchors_in(refs, labels),
                    }
                )
        for unit_id in vocabulary.keys() - {unit["id"] for unit in units}:
            self.problems.append(
                f"Section 7 gives a vocabulary for {unit_id}, which is not a unit."
            )
        return units

    def _prerequisites(self, cell: str, unit_id: str) -> list[str]:
        text = _plain(cell)
        if text == "لا شيء":
            return []
        ids = _UNIT_ID.findall(text)
        if not ids or _UNIT_ID.sub("", text).replace("،", "").strip():
            self.problems.append(
                f"The prerequisites of {unit_id} are neither «لا شيء» nor unit ids: «{text}»."
            )
        return ids

    def _reference_anchors(self, rows: list[list[str]]) -> dict[str, str]:
        """Map the text of every link in the reference cells to its anchor."""
        labels: dict[str, str] = {}
        for row in rows:
            for text, url in _LINK.findall(row[3] if len(row) > 3 else ""):
                anchor = anchor_of(url)
                if anchor is None:
                    self.problems.append(
                        f"The link «{text}» ({url}) is not a quran.com or sunnah.com address the parser reads."
                    )
                elif labels.setdefault(text, anchor) != anchor:
                    self.problems.append(
                        f"The reference «{text}» points at two places: {labels[text]} and {anchor}."
                    )
        return labels

    def vocabulary(self) -> dict[str, list[str]]:
        text = " ".join(self.section("آلية استخراج القيم").body)
        quoted = {
            item.strip()
            for match in re.finditer(r"«([^»]+)»", text)
            for item in match.group(1).split("،")
        }
        for unit_id, words in SECTION_7_VOCABULARY.items():
            missing = [word for word in words if word not in quoted]
            if unit_id not in text or missing:
                self.problems.append(
                    f"Section 7 no longer gives the vocabulary of {unit_id} ({', '.join(missing) or 'the unit'})."
                )
        return {unit_id: list(words) for unit_id, words in SECTION_7_VOCABULARY.items()}

    # ─── Coverage ───

    def coverage(self, units: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_domain: dict[str, list[str]] = {}
        for unit in units:
            by_domain.setdefault(unit["domain"], []).append(unit["id"])
        every = [unit["id"] for unit in units]
        rules = []
        for row in _table(self.section("ضبط التغطية")):
            asset = _plain(row[0])
            matches = list(_ID_OR_RANGE.finditer(row[1]))
            if not matches:
                self.problems.append(
                    f"The coverage rule «{asset}» names no domain or unit: «{_plain(row[1])}»."
                )
                continue
            expanded = [unit for match in matches for unit in self._expand(match, by_domain, every)]
            refs = [match.group(0).replace("`", "") for match in matches]
            rules.append({"asset": asset, "refs": refs, "units": list(dict.fromkeys(expanded))})
        return rules

    def _expand(
        self, match: re.Match[str], by_domain: dict[str, list[str]], every: list[str]
    ) -> list[str]:
        """Return the units a coverage reference stands for: a unit, a domain, or a range of either."""
        first, last = match.group(1), match.group(2) or match.group(1)
        known = by_domain.keys() if "_" not in first else every
        if first not in known or last not in known:
            self.problems.append(f"A coverage rule names {first} or {last}, which does not exist.")
            return []
        if "_" in first:
            return every[every.index(first) : every.index(last) + 1]
        return [
            unit for domain in by_domain if first <= domain <= last for unit in by_domain[domain]
        ]


# ─── References ───


def anchor_of(url: str) -> str | None:
    """Return the anchor of a reading link (`Q:17:36`, `H:muslim:8a`); None for one it cannot read."""
    if match := _SUNNAH.match(url):
        return f"H:{match.group('collection')}:{match.group('number')}"
    if match := _QURAN.match(url):
        surah = match.group("surah")
        number = surah if surah.isdigit() else SURAH_NUMBER_BY_SLUG.get(surah)
        if number is None:
            return None
        verses = match.group("verses")
        return f"Q:{number}:{verses}" if verses else f"Q:{number}"
    return None


def _split_references(cell: str) -> list[str]:
    """Split a reference cell at its commas, keeping the commas inside a link text together."""
    parts, depth, current = [], 0, ""
    for char in cell:
        depth += char == "["
        depth -= char == "]"
        if char == "،" and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return [text for part in parts if (text := _plain(part))]


def _anchors_in(refs: list[str], labels: dict[str, str]) -> list[str]:
    """Return, in order, the anchors of the known references mentioned in `refs`."""
    if not labels:
        return []
    ordered = sorted(labels, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(label) for label in ordered) + r"(?![0-9A-Za-z])")
    found = [labels[match.group(0)] for ref in refs for match in pattern.finditer(ref)]
    return list(dict.fromkeys(found))


# ─── The whole document ───


def parse_masar(
    text: str, *, source_name: str, path_version: str | None = None
) -> LearningPathFile:
    """
    Parse the document `text`; `source_name` is recorded as the file it came from.

    The path version defaults to `tabsira-masar-<version>`, the version the document
    states. Raises `MasarParseError` listing everything it could not read.
    """
    reader = _Reader(text)
    title = next((s.title for s in reader.sections if s.level == 1), None)
    if title is None:
        reader.problems.append("The document has no title (a heading of level 1).")
    reference_id, version = reader.meta("معرّف المرجع"), reader.meta("الإصدار")
    description, released_on = reader.meta("الغرض"), reader.released_on()

    depths = reader.depths()
    domains, sections = reader.domains()
    units = reader.units(domains, sections, [depth["code"] for depth in depths])
    coverage = reader.coverage(units)
    stated = _STATED_COUNTS.search(text)
    if stated and (int(stated.group(1)), int(stated.group(2))) != (len(domains), len(units)):
        reader.problems.append(
            f"The introduction states {stated.group(1)} domains and {stated.group(2)} units; "
            f"the tables hold {len(domains)} and {len(units)}."
        )
    if reader.problems:
        raise MasarParseError(reader.problems)

    data = {
        "path_version": path_version or f"tabsira-masar-{version}",
        "title": title,
        "version": version,
        "released_on": released_on,
        "description": description,
        "source": {
            "file": source_name,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "reference_id": (reference_id or "").strip("`"),
        },
        "counts": {"domains": len(domains), "units": len(units)},
        "depths": depths,
        "domains": domains,
        "units": units,
        "coverage": coverage,
    }
    try:
        return LearningPathFile.model_validate(data)
    except ValidationError as error:
        problems = [f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in error.errors()]
        raise MasarParseError(problems) from None
