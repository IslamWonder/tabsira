"""
The shape of a learning path file (`data/masar/<path_version>.json`).

One file is one path version. The structure is checked here; what must hold across
the whole file (ids, prerequisites, cycles, coverage) is checked by
`src.services.masar_validator`. A new monthly release is a new file of this shape:
more domains and units, no change to the code.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

DEPTH_CODE = r"^L[0-9]$"
DOMAIN_ID = r"^T[0-9]{2}$"
UNIT_ID = r"^T[0-9]{2}_[0-9]{2}$"
# Q:<surah>[:<verse>[-<verse>]] and H:<collection>:<number>: pointers, never text.
SOURCE_ANCHOR = r"^(Q:[0-9]{1,3}(:[0-9]{1,3}(-[0-9]{1,3})?)?|H:[a-z]+:[0-9]+[a-z]?)$"

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Source(_Strict):
    """The document the data was made from."""

    file: Text
    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    reference_id: Text


class Counts(_Strict):
    """What the file says it holds; the validator checks it against what it holds."""

    domains: int = Field(ge=1)
    units: int = Field(ge=1)


class Depth(_Strict):
    """One of the depths a unit can be learnt at (L0 to L5 in version 1.0)."""

    code: Annotated[str, StringConstraints(pattern=DEPTH_CODE)]
    name: Text
    ability: Text
    example: Text


class Domain(_Strict):
    """A domain: which side of Islam a group of units is about."""

    id: Annotated[str, StringConstraints(pattern=DOMAIN_ID)]
    order: int = Field(ge=1)
    title: Text
    function: Text
    goal: Text
    concepts: list[Text]


class Unit(_Strict):
    """A unit: one definite thing to understand, inside a domain."""

    id: Annotated[str, StringConstraints(pattern=UNIT_ID)]
    domain: Annotated[str, StringConstraints(pattern=DOMAIN_ID)]
    order: int = Field(ge=1)
    title: Text
    objectives: Annotated[list[Text], Field(min_length=1)]
    prerequisites: list[Annotated[str, StringConstraints(pattern=UNIT_ID)]]
    depths: Annotated[
        list[Annotated[str, StringConstraints(pattern=DEPTH_CODE)]], Field(min_length=1)
    ]
    concepts: list[Text]
    # Pointers for retrieval and review, as text: never the text of a verse or a hadith.
    evidence_refs: list[Text]
    source_anchors: list[Annotated[str, StringConstraints(pattern=SOURCE_ANCHOR)]]


class CoverageRule(_Strict):
    """An essential part of the faith that the path must keep covered, and where."""

    asset: Text
    refs: Annotated[list[Text], Field(min_length=1)]
    units: Annotated[list[Annotated[str, StringConstraints(pattern=UNIT_ID)]], Field(min_length=1)]


class LearningPathFile(_Strict):
    """A whole path version."""

    path_version: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9.-]{2,62}$")]
    title: Text
    version: Text
    released_on: date | None
    description: Text | None
    source: Source
    counts: Counts
    depths: Annotated[list[Depth], Field(min_length=1)]
    domains: Annotated[list[Domain], Field(min_length=1)]
    units: Annotated[list[Unit], Field(min_length=1)]
    coverage: list[CoverageRule]


def _line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def dumps(path: LearningPathFile) -> str:
    """
    Return the file text: the same bytes for the same data, one domain or unit per line.

    There is no timestamp, so a regenerated file differs from the committed one only
    when the document it was made from changed.
    """
    data = path.model_dump(mode="json")
    head = {
        key: data[key] for key in ("path_version", "title", "version", "released_on", "description")
    }
    parts = [f"  {_line(key)}: {_line(value)}" for key, value in head.items()]
    parts.append(f'  "source": {_line(data["source"])}')
    parts.append(f'  "counts": {_line(data["counts"])}')
    for key in ("depths", "domains", "units", "coverage"):
        items = ",\n".join(f"    {_line(item)}" for item in data[key])
        parts.append(f'  "{key}": [\n{items}\n  ]' if items else f'  "{key}": []')
    return "{\n" + ",\n".join(parts) + "\n}\n"
