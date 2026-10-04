"""
DetectorClient: the object detector of services/vision, over HTTP.

Boxes help the scene analyzer anchor what it names, but a scan never waits on
them: a detector that is down, slow or answers nonsense is skipped, and the
result says so (`available=False` with the reason). The image sent is the
stripped model copy, never the original upload.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic.alias_generators import to_camel

from src.pipeline.schemas import BBox, Detection, DetectorRequest, DetectorResult

log = logging.getLogger("tabsira.pipeline.detector")


class _Wire(BaseModel):
    """The service's camelCase answer (services/vision/src/vision/schemas.py)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class _WireDetection(_Wire):
    id: str
    label: str
    label_arabic: str | None
    confidence: float
    bbox: BBox


class _WireResponse(_Wire):
    detections: list[_WireDetection]
    model: str
    ms: int


class DetectorClient:
    """Calls `POST /detect` on the vision service."""

    def __init__(
        self,
        base_url: str,
        http: httpx.AsyncClient,
        *,
        timeout_seconds: float,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._url = base_url.rstrip("/") + "/detect"
        self._http = http
        self._timeout = timeout_seconds
        self._clock = clock

    async def detect(self, request: DetectorRequest) -> DetectorResult:
        """Return the detections, or an unavailable result naming why there are none."""
        started = self._clock()
        form: dict[str, str] = {}
        if request.vocabulary is not None:
            form["vocabulary"] = ",".join(request.vocabulary)
        if request.confidence is not None:
            form["conf"] = str(request.confidence)
        if request.max_detections is not None:
            form["max_detections"] = str(request.max_detections)
        files = {"image": ("image.jpg", request.image.data, request.image.mime)}

        try:
            response = await self._http.post(
                self._url, data=form, files=files, timeout=self._timeout
            )
        except httpx.TimeoutException:
            return self._skipped("timeout", started)
        except httpx.TransportError:
            return self._skipped("unreachable", started)
        if response.status_code != httpx.codes.OK:
            return self._skipped(f"http_{response.status_code}", started)
        try:
            wire = _WireResponse.model_validate_json(response.content)
        except ValidationError:
            return self._skipped("invalid_response", started)

        detections = [
            Detection(
                id=item.id,
                label=item.label,
                label_arabic=item.label_arabic,
                confidence=min(max(item.confidence, 0.0), 1.0),
                bbox=item.bbox,
            )
            for item in wire.detections
        ]
        return DetectorResult(
            available=True,
            detections=detections,
            model=wire.model,
            detector_ms=wire.ms,
            latency_ms=self._elapsed(started),
        )

    def _skipped(self, reason: str, started: float) -> DetectorResult:
        log.warning("detector skipped: %s", reason)
        return DetectorResult(available=False, latency_ms=self._elapsed(started), error=reason)

    def _elapsed(self, started: float) -> int:
        return round((self._clock() - started) * 1000)
