"""
The vision service: object detection over HTTP.

Run it from `services/vision`:

    uv run vision                                                   # settings from the environment
    uv run uvicorn vision.main:create_app --factory --reload        # development, with reload
"""

from __future__ import annotations

import base64
import binascii
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated

import uvicorn
from fastapi import FastAPI, File, Form, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartParser

from vision.config import MAX_DETECTIONS_LIMIT, MAX_VOCABULARY, Settings
from vision.detector import Detector, UltralyticsDetector
from vision.errors import DetectorUnavailableError, RerankerUnavailableError, VisionError
from vision.images import decode_image
from vision.reranker import Reranker, TransformersReranker
from vision.schemas import (
    DetectJsonRequest,
    DetectResponse,
    ErrorResponse,
    HealthResponse,
    RerankRequest,
    RerankResponse,
)
from vision.vocabulary import normalise_vocabulary

logger = logging.getLogger("vision")

# Room for the form fields around an upload, and for base64 inflating a body by a third.
BODY_OVERHEAD_BYTES = 64 * 1024

ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    status: {"model": ErrorResponse} for status in (400, 413, 415, 422, 503)
}


def configure_logging() -> None:
    """Give the `vision` logger a stderr handler once, so INFO lines show under any server."""
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def error_response(status: int, code: str, detail: str) -> JSONResponse:
    """Build the body every error shares."""
    return JSONResponse(status_code=status, content={"error": code, "detail": detail})


def decode_base64(payload: str) -> bytes:
    """Decode bare base64 or a `data:image/...;base64,` URL."""
    text = payload.strip()
    if text.startswith("data:") and "," in text:
        text = text.split(",", 1)[1]
    try:
        return base64.b64decode("".join(text.split()), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise VisionError(400, "invalid_base64", "imageBase64 is not valid base64.") from exc


def register_error_handlers(app: FastAPI) -> None:
    """Make every error, including the framework's own, `{"error": code, "detail": message}`."""

    @app.exception_handler(VisionError)
    async def vision_error(_: Request, exc: VisionError) -> JSONResponse:
        if exc.status >= 500:
            logger.error("%s: %s", exc.code, exc.detail)
        return error_response(exc.status, exc.code, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'][1:])}: {error['msg']}"
            for error in exc.errors()
        )
        return error_response(422, "invalid_request", problems)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled error", exc_info=exc)
        return error_response(500, "internal_error", "The detection failed unexpectedly.")


def run_detection(
    settings: Settings,
    detector: Detector,
    data: bytes,
    vocabulary: str | list[str] | None,
    conf: float | None,
    max_detections: int | None,
) -> DetectResponse:
    """Validate the image and the vocabulary, detect, and build the response."""
    labels = normalise_vocabulary(vocabulary)
    if len(labels) > MAX_VOCABULARY:
        message = f"At most {MAX_VOCABULARY} labels are allowed."
        raise VisionError(422, "vocabulary_too_large", message)
    image = decode_image(
        data,
        max_bytes=settings.vision_max_image_bytes,
        max_pixels=settings.vision_max_image_pixels,
    )
    result = detector.detect(
        image,
        labels,
        settings.detector_conf if conf is None else conf,
        settings.detector_max_detections if max_detections is None else max_detections,
    )
    return DetectResponse(
        detections=result.detections,
        width=image.width,
        height=image.height,
        model=result.model,
        ms=result.ms,
        vocabulary_mode=result.vocabulary_mode,
    )


def create_app(
    settings: Settings | None = None,
    detector: Detector | None = None,
    reranker: Reranker | None = None,
) -> FastAPI:
    """Build the application; tests pass their own settings, detector and reranker."""
    configure_logging()
    settings = settings or Settings()
    detector = detector or UltralyticsDetector(settings)
    reranker = reranker or TransformersReranker(settings)
    max_body = settings.vision_max_image_bytes * 4 // 3 + BODY_OVERHEAD_BYTES
    # Starlette writes an upload to a temporary file once it passes 1 MB. A photo is
    # kept in memory instead, up to the size that is accepted at all.
    MultiPartParser.spool_max_size = max_body

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if settings.vision_warmup:
            try:
                await run_in_threadpool(detector.warmup)
            except DetectorUnavailableError as exc:
                logger.warning("warm-up skipped: %s", exc.detail)
        if settings.vision_reranker_warmup:
            try:
                await run_in_threadpool(reranker.warmup)
            except RerankerUnavailableError as exc:
                logger.warning("reranker warm-up skipped: %s", exc.detail)
        yield

    app = FastAPI(title="TABSIRA vision", version="0.1.0", lifespan=lifespan)
    register_error_handlers(app)

    @app.middleware("http")
    async def refuse_huge_bodies(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Before the body is parsed and spooled, so a giant upload costs nothing.
        length = request.headers.get("content-length", "0")
        if length.isdigit() and int(length) > max_body:
            return error_response(413, "image_too_large", "The request body is too large.")
        return await call_next(request)

    # The routes are plain `def`, so FastAPI runs them in a worker thread: the event
    # loop, and with it /health, stays responsive while a detection runs.

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        status = detector.status()
        ranking = reranker.status()
        return HealthResponse(
            ok=status.error is None,
            detector=status.name,
            model=status.model,
            device=status.device,
            model_loaded=status.loaded,
            vocabulary_size=status.vocabulary_size,
            vocabulary_mode=status.vocabulary_mode,
            error=status.error,
            reranker=ranking.model,
            reranker_loaded=ranking.loaded,
            reranker_error=ranking.error,
        )

    @app.post("/detect", response_model=DetectResponse, responses=ERROR_RESPONSES)
    def detect(
        image: Annotated[UploadFile, File(description="JPEG, PNG or WebP")],
        vocabulary: Annotated[str | None, Form(description="Comma-separated labels")] = None,
        conf: Annotated[float | None, Form(ge=0, le=1)] = None,
        max_detections: Annotated[int | None, Form(ge=1, le=MAX_DETECTIONS_LIMIT)] = None,
    ) -> DetectResponse:
        data = image.file.read(settings.vision_max_image_bytes + 1)
        return run_detection(settings, detector, data, vocabulary, conf, max_detections)

    @app.post("/detect-json", response_model=DetectResponse, responses=ERROR_RESPONSES)
    def detect_json(body: DetectJsonRequest) -> DetectResponse:
        data = decode_base64(body.image_base64)
        return run_detection(
            settings, detector, data, body.vocabulary, body.conf, body.max_detections
        )

    @app.post("/rerank", response_model=RerankResponse, responses=ERROR_RESPONSES)
    def rerank(body: RerankRequest) -> RerankResponse:
        result = reranker.rerank(body.query, body.passages)
        return RerankResponse(scores=result.scores, model=result.model, ms=result.ms)

    return app


def run() -> None:
    """Serve the application on the configured loopback address (`uv run vision`)."""
    settings = Settings()
    uvicorn.run(
        "vision.main:create_app",
        factory=True,
        host=settings.vision_host,
        port=settings.vision_port,
    )
