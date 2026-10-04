"""
The browser family of a `User-Agent` header, and nothing else.

A full user agent string narrows a person down (browser build, operating system,
device model), so the API keeps only the family: enough to tell a Safari bug from
a Firefox one, too little to recognise anyone. Used by the cookie-consent record
and by the browser error reports.
"""

from __future__ import annotations

import re

OTHER = "other"

# Longer than any real header; the rest is ignored rather than scanned.
_MAX_HEADER_LENGTH = 512

# Order matters: Edge, Opera and Samsung Internet all say "Chrome" and "Safari"
# too, and Chrome says "Safari".
_FAMILIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("edge", re.compile(r"\b(?:Edg|EdgA|EdgiOS|Edge)/")),
    ("opera", re.compile(r"\b(?:OPR|OPT|Opera)/")),
    ("samsung_internet", re.compile(r"\bSamsungBrowser/")),
    ("firefox", re.compile(r"\b(?:Firefox|FxiOS)/")),
    ("chrome", re.compile(r"\b(?:Chrome|CriOS|Chromium)/")),
    ("safari", re.compile(r"\bSafari/")),
)

FAMILIES = frozenset([name for name, _ in _FAMILIES] + [OTHER])


def user_agent_family(header: str | None) -> str:
    """Return one of `FAMILIES` for a `User-Agent` header; `other` when it is unknown or absent."""
    if not header:
        return OTHER
    text = header[:_MAX_HEADER_LENGTH]
    for name, pattern in _FAMILIES:
        if pattern.search(text):
            return name
    return OTHER
