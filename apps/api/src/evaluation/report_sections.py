"""
Sections of a generated Markdown report that another command owns.

docs/BENCHMARK.md is written whole by the scene benchmark, and the retrieval
benchmark adds its own section to it. A section sits between two comment
markers (`<!-- section:retrieval -->` ... `<!-- /section:retrieval -->`): the
command that owns it replaces it in place, and a command that rewrites the
whole file carries every section over from the file it replaces.
"""

from __future__ import annotations

import re

_SECTION = re.compile(r"<!-- section:([a-z0-9-]+) -->\n.*?<!-- /section:\1 -->\n", re.DOTALL)


def wrap(name: str, body: str) -> str:
    """Return `body` between the markers of section `name`."""
    return f"<!-- section:{name} -->\n{body.rstrip()}\n<!-- /section:{name} -->\n"


def sections(document: str) -> dict[str, str]:
    """Return every marked section of `document`, markers included, by name."""
    return {match.group(1): match.group(0) for match in _SECTION.finditer(document)}


def replace_section(document: str, name: str, body: str) -> str:
    """Put section `name` in `document`: in place when it is there, at the end otherwise."""
    block = wrap(name, body)
    existing = sections(document).get(name)
    if existing is not None:
        return document.replace(existing, block)
    return f"{document.rstrip()}\n\n{block}"


def carry_sections(previous: str, rewritten: str) -> str:
    """Append to `rewritten` the sections of `previous` it does not hold itself."""
    kept = rewritten
    for name, block in sections(previous).items():
        if name not in sections(kept):
            kept = f"{kept.rstrip()}\n\n{block}"
    return kept
