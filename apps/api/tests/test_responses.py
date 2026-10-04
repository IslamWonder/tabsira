from __future__ import annotations

from src.responses import OrjsonResponse


def test_orjson_response_renders_compact_json_with_integer_keys():
    response = OrjsonResponse({"status": "ok", 1: ["a", None]})

    assert response.body == b'{"status":"ok","1":["a",null]}'
    assert response.media_type == "application/json"
