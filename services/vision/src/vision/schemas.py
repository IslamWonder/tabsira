"""Request and response models. Field names are camelCase on the wire, like the API's."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from vision.config import MAX_DETECTIONS_LIMIT, MAX_PASSAGE_CHARS, MAX_PASSAGES, MAX_QUERY_CHARS


class VocabularyMode(StrEnum):
    """Which label set the last detection scored against."""

    UNLOADED = "unloaded"  # no model yet
    OPEN = "open"  # the requested vocabulary, encoded by the text encoder
    COCO = "coco"  # the 80 COCO classes of the checkpoint: the text encoder is unavailable


class CamelModel(BaseModel):
    """Base of every wire model: camelCase on the wire, snake_case in code."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class BBox(CamelModel):
    """A box as ratios (0 to 1) of the image that was received; x and y are its top-left corner."""

    x: float
    y: float
    width: float
    height: float


class Detection(CamelModel):
    """One object found in the image."""

    id: str
    label: str
    label_arabic: str | None
    confidence: float
    bbox: BBox


class DetectResponse(CamelModel):
    """Result of a detection: boxes are ratios of the image after its EXIF orientation is applied."""

    detections: list[Detection]
    width: int
    height: int
    model: str
    ms: int
    vocabulary_mode: VocabularyMode


class DetectJsonRequest(CamelModel):
    """Body of `POST /detect-json`."""

    image_base64: Annotated[str, Field(min_length=1)]
    vocabulary: list[str] | str | None = None
    conf: Annotated[float | None, Field(ge=0, le=1)] = None
    max_detections: Annotated[int | None, Field(ge=1, le=MAX_DETECTIONS_LIMIT)] = None


class HealthResponse(CamelModel):
    """State of the service and of its detector."""

    ok: bool
    detector: str
    model: str
    device: str
    model_loaded: bool
    vocabulary_size: int
    vocabulary_mode: VocabularyMode
    error: str | None = None
    # The reranker of POST /rerank, reported apart: `ok` speaks for the detector.
    reranker: str = ""
    reranker_loaded: bool = False
    reranker_error: str | None = None


class RerankRequest(CamelModel):
    """Body of `POST /rerank`: one query and the passages to score against it."""

    query: Annotated[str, Field(min_length=1, max_length=MAX_QUERY_CHARS)]
    passages: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=MAX_PASSAGE_CHARS)]],
        Field(min_length=1, max_length=MAX_PASSAGES),
    ]


class RerankResponse(CamelModel):
    """One relevance score from 0 to 1 per passage, in the order the passages were sent."""

    scores: list[float]
    model: str
    ms: int


class ErrorResponse(BaseModel):
    """Every error body."""

    error: str
    detail: str
