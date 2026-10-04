"""JSON response class that serialises with orjson."""

from __future__ import annotations

from typing import Any

import orjson
from fastapi.responses import JSONResponse


class OrjsonResponse(JSONResponse):
    """
    JSON response rendered by orjson, which is faster than the standard library.

    FastAPI's own ORJSONResponse is deprecated, so this is the small subclass
    of JSONResponse that does the same job.
    """

    def render(self, content: Any) -> bytes:
        return orjson.dumps(content, option=orjson.OPT_NON_STR_KEYS)
