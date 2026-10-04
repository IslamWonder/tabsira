"""
The JSON form of a public id (`src.models.public_id`): a decimal string.

A public id is a 64-bit integer, beyond the 2^53 integers JavaScript holds
exactly, so responses carry it as a string and the OpenAPI schema says so; the
generated web client then types it as a string. Requests may send the string or
the number.
"""

from __future__ import annotations

import re
from typing import Annotated, Any

from pydantic import BeforeValidator, PlainSerializer, WithJsonSchema

MAX_PUBLIC_ID = 2**63 - 1
_DIGITS = re.compile(r"[1-9][0-9]{0,18}")


def parse_public_id(value: Any) -> int:
    """Return `value` as a public id, or raise `ValueError`."""
    if isinstance(value, bool):
        message = "a public id is not a boolean"
        raise ValueError(message)  # noqa: TRY004 - pydantic reports a ValueError as a 422
    if isinstance(value, str):
        if not _DIGITS.fullmatch(value):
            message = "a public id is a positive decimal number"
            raise ValueError(message)
        value = int(value)
    if not isinstance(value, int) or not 1 <= value <= MAX_PUBLIC_ID:
        message = "a public id is a positive 64-bit number"
        raise ValueError(message)
    return value


PublicId = Annotated[
    int,
    BeforeValidator(parse_public_id),
    PlainSerializer(str, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "pattern": "^[1-9][0-9]{0,18}$"}),
]
