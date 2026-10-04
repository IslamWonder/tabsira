"""The clock, in one place so a test can move time without sleeping."""

from __future__ import annotations

import time
from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current time, timezone-aware, in UTC."""
    return datetime.now(UTC)


def monotonic() -> float:
    """Return seconds from a clock that never goes back, for measuring how long ago."""
    return time.monotonic()
