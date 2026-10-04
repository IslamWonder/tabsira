from __future__ import annotations

import logging

import httpx
import pytest

from src.pipeline.detector import DetectorClient
from src.pipeline.schemas import BBox, Detection, DetectorRequest, EncodedImage

IMAGE = EncodedImage(data=b"\xff\xd8jpeg-bytes", width=1344, height=768)
ANSWER = {
    "detections": [
        {
            "id": "d1",
            "label": "smartphone",
            "labelArabic": "هاتف ذكي",
            "confidence": 0.75,
            "bbox": {"x": 0.3, "y": 0.29, "width": 0.38, "height": 0.37},
        },
        {
            "id": "d2",
            "label": "kettle",
            "labelArabic": None,
            "confidence": 1.0000001,
            "bbox": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
        },
    ],
    "width": 1344,
    "height": 768,
    "model": "yoloe-11s-seg",
    "ms": 131,
    "vocabularyMode": "open",
}


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 0.1
        return self.now


async def detect(handler, request: DetectorRequest | None = None):
    seen: list[httpx.Request] = []

    def record(incoming: httpx.Request) -> httpx.Response:
        seen.append(incoming)
        return handler(incoming)

    async with httpx.AsyncClient(transport=httpx.MockTransport(record)) as http:
        client = DetectorClient("http://127.0.0.1:8100/", http, timeout_seconds=5, clock=Clock())
        result = await client.detect(request or DetectorRequest(image=IMAGE))
    return result, seen


async def test_detections_are_read_from_the_vision_service():
    result, seen = await detect(lambda _: httpx.Response(200, json=ANSWER))

    assert result.available
    assert result.error is None
    assert result.model == "yoloe-11s-seg"
    assert result.detector_ms == 131
    assert result.latency_ms == 100
    assert result.detections == [
        Detection(
            id="d1",
            label="smartphone",
            label_arabic="هاتف ذكي",
            confidence=0.75,
            bbox=BBox(x=0.3, y=0.29, width=0.38, height=0.37),
        ),
        Detection(
            id="d2",
            label="kettle",
            label_arabic=None,
            confidence=1.0,
            bbox=BBox(x=0.0, y=0.0, width=1.0, height=1.0),
        ),
    ]
    request = seen[0]
    assert str(request.url) == "http://127.0.0.1:8100/detect"
    body = request.content
    assert b'name="image"; filename="image.jpg"' in body
    assert b"\xff\xd8jpeg-bytes" in body
    # Nothing but the image is sent when the request leaves the defaults to the service.
    assert b'name="vocabulary"' not in body
    assert b'name="conf"' not in body


async def test_vocabulary_confidence_and_limit_are_sent_as_form_fields():
    request = DetectorRequest(
        image=IMAGE, vocabulary=["olive", "rain"], confidence=0.3, max_detections=5
    )

    _, seen = await detect(lambda _: httpx.Response(200, json=ANSWER), request)

    body = seen[0].content.decode("latin-1")
    assert 'name="vocabulary"\r\n\r\nolive,rain' in body
    assert 'name="conf"\r\n\r\n0.3' in body
    assert 'name="max_detections"\r\n\r\n5' in body


def raises(error: Exception):
    def handler(_: httpx.Request) -> httpx.Response:
        raise error

    return handler


@pytest.mark.parametrize(
    ("handler", "reason"),
    [
        (raises(httpx.ReadTimeout("slow")), "timeout"),
        (raises(httpx.ConnectError("refused")), "unreachable"),
        (lambda _: httpx.Response(503, json={"error": "detector_unavailable"}), "http_503"),
        (lambda _: httpx.Response(200, text="<html>"), "invalid_response"),
        (lambda _: httpx.Response(200, json={"detections": "none"}), "invalid_response"),
        (
            lambda _: httpx.Response(
                200,
                json={**ANSWER, "detections": [{**ANSWER["detections"][0], "bbox": {"x": 2}}]},
            ),
            "invalid_response",
        ),
    ],
)
async def test_a_detector_that_fails_is_skipped_with_its_reason(handler, reason, caplog):
    with caplog.at_level(logging.WARNING, logger="tabsira.pipeline.detector"):
        result, _ = await detect(handler)

    assert not result.available
    assert result.detections == []
    assert result.error == reason
    assert result.latency_ms == 100
    assert f"detector skipped: {reason}" in caplog.text
