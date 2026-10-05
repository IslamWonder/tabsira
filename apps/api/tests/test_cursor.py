"""Keyset cursors: opaque, and refused when this API did not write them."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import pytest

from src.errors import AppError, ErrorCode
from src.services import cursor as cursors

MOMENT = datetime(2026, 10, 4, 12, 30, 15, 123456, tzinfo=UTC)
IDENT = 114564384939048960


def encoded(**body):
    raw = json.dumps({"t": MOMENT.isoformat(), "i": IDENT, "a": None, "s": None, **body})
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def test_a_cursor_round_trips_with_its_time_and_id():
    cursor = cursors.Cursor(at=MOMENT, id=IDENT)

    text = cursors.encode(cursor)

    assert cursors.decode(text) == cursor
    assert "=" not in text
    assert str(IDENT) not in text  # opaque, not the bare id


def test_a_ranked_cursor_keeps_when_it_was_ranked_and_the_last_score():
    cursor = cursors.Cursor(at=MOMENT, id=IDENT, as_of=MOMENT, score=0.731245)

    assert cursors.decode(cursors.encode(cursor)) == cursor
    assert cursors.decode(encoded(s=2)).score == 2.0


def test_no_cursor_is_no_position():
    assert cursors.decode(None) is None


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "!!!",
        "bm90LWpzb24",
        base64.urlsafe_b64encode(b"[1, 2]").decode(),
        base64.urlsafe_b64encode(b'{"t": "x"}').decode(),
        encoded(i="not-a-number"),
        encoded(i=True),
        encoded(i=0),
        encoded(i=-3),
        encoded(i=1.5),
        encoded(i=2**63),
        encoded(t="yesterday"),
        encoded(t="2026-10-04T12:00:00"),
        encoded(a="2026-10-04T12:00:00"),
        encoded(a="whenever"),
        encoded(s="high"),
        encoded(s=True),
        encoded(s=10**400),
        encoded(s=float("nan")),
        encoded(s=float("inf")),
    ],
)
def test_a_cursor_this_api_did_not_write_is_refused(raw):
    with pytest.raises(AppError) as caught:
        cursors.decode(raw)

    assert (caught.value.code, caught.value.status_code) == (ErrorCode.INVALID_CURSOR, 400)
