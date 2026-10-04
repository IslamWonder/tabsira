"""Errors the service reports to its callers as `{"error": code, "detail": message}`."""

from __future__ import annotations


class VisionError(Exception):
    """A failure with an HTTP status and a stable machine-readable code."""

    def __init__(self, status: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail


class DetectorUnavailableError(VisionError):
    """The model cannot be loaded or has no usable vocabulary; callers should try later."""

    def __init__(self, detail: str) -> None:
        super().__init__(503, "detector_unavailable", detail)
