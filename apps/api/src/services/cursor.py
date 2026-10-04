"""
Keyset cursors: where the last page ended, as an opaque string.

A page ends at an `(at, id)` pair: the time that orders the list and the id that breaks a tie.
Asking for what comes after that pair never skips or repeats an item when the list changes
between two pages, which an offset does. A ranked list also pins the moment it was ranked
(`as_of`) and the score of the last item, so the order the reader scrolls through is the
order that was computed. The cursor is only a position: it grants nothing, and a forged one
can only move the reader around a list they may already read.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime

from src.errors import AppError, ErrorCode


@dataclass(frozen=True)
class Cursor:
    at: datetime
    id: int
    # Only the ranked feed: the moment it was ranked, and the score of the last item.
    as_of: datetime | None = None
    score: float | None = None


def invalid() -> AppError:
    return AppError(ErrorCode.INVALID_CURSOR, "The cursor is not valid.", status_code=400)


def encode(cursor: Cursor) -> str:
    """Return the cursor as URL-safe text."""
    body = {
        "t": cursor.at.isoformat(),
        "i": cursor.id,
        "a": cursor.as_of.isoformat() if cursor.as_of else None,
        "s": cursor.score,
    }
    raw = json.dumps(body, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode(raw: str | None) -> Cursor | None:
    """Read a cursor back; None for no cursor, 400 for one this API did not write."""
    if raw is None:
        return None
    try:
        padded = raw + "=" * (-len(raw) % 4)
        body = json.loads(base64.urlsafe_b64decode(padded.encode()))
        at = datetime.fromisoformat(body["t"])
        cursor_id = body["i"]
        as_of = None if body["a"] is None else datetime.fromisoformat(body["a"])
        score = body["s"]
    except (ValueError, KeyError, TypeError, binascii.Error):
        raise invalid() from None
    # A time with no zone cannot be compared with the database's times without a guess.
    zoned = at.tzinfo is not None and (as_of is None or as_of.tzinfo is not None)
    numeric = score is None or (isinstance(score, int | float) and not isinstance(score, bool))
    identified = isinstance(cursor_id, int) and not isinstance(cursor_id, bool) and cursor_id >= 1
    if not zoned or not numeric or not identified:
        raise invalid()
    return Cursor(at=at, id=cursor_id, as_of=as_of, score=None if score is None else float(score))
