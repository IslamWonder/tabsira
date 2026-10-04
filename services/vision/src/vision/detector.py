"""
The object detector: a `Detector` protocol and its Ultralytics implementation.

Heavy imports (torch, Ultralytics) happen when the model is first needed, so the
process starts at once and `/health` never waits for them.

A vision model returns boxes in pixels of the image it received. They are turned
into 0 to 1 ratios of that image here, boxes outside the image are dropped, and
the rest are clamped to it.
"""

from __future__ import annotations

import importlib
import logging
import math
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from PIL import Image

from vision.config import ModelFamily, Settings, family_of
from vision.errors import DetectorUnavailableError
from vision.schemas import BBox, Detection, VocabularyMode
from vision.vocabulary import DEFAULT_VOCABULARY, arabic_label
from vision.weights import ENCODER_FILES, configure_ultralytics, encoder_ready

logger = logging.getLogger(__name__)

# Builds the Ultralytics model of a family from a checkpoint file.
ModelLoader = Callable[[ModelFamily, Path], Any]

# Decimal places of a ratio: 0.0001 of a 4000 px photo is under half a pixel.
RATIO_DIGITS = 4


@dataclass(frozen=True)
class DetectionResult:
    """What one call to `Detector.detect` returns."""

    detections: list[Detection]
    model: str
    ms: int  # time spent in the detector: loading, encoding a new vocabulary, inference
    vocabulary_mode: VocabularyMode


@dataclass(frozen=True)
class DetectorStatus:
    """What `/health` reports about the detector."""

    name: str
    model: str
    device: str
    loaded: bool
    vocabulary_size: int
    vocabulary_mode: VocabularyMode
    error: str | None


class Detector(Protocol):
    """What the service needs from a detector, so that one can be swapped for another."""

    def warmup(self) -> None:
        """Load the model now instead of on the first request."""
        ...

    def status(self) -> DetectorStatus:
        """Describe the detector without loading it."""
        ...

    def detect(
        self,
        image: Image.Image,
        vocabulary: Sequence[str],
        conf: float,
        max_detections: int,
    ) -> DetectionResult:
        """Find the objects of `vocabulary` in an RGB image; raise DetectorUnavailableError when it cannot."""
        ...


def ratio_box(x1: float, y1: float, x2: float, y2: float, width: int, height: int) -> BBox | None:
    """
    Turn a pixel box into ratios of the image, or return None when it is not inside it.

    A box that lies outside the image, is empty or has a non-finite corner is dropped;
    one that only crosses the border is clamped to it.
    """
    if not all(math.isfinite(value) for value in (x1, y1, x2, y2)):
        return None
    left = round(max(x1, 0) / width, RATIO_DIGITS)
    top = round(max(y1, 0) / height, RATIO_DIGITS)
    right = round(min(x2, width) / width, RATIO_DIGITS)
    bottom = round(min(y2, height) / height, RATIO_DIGITS)
    # Outside the image, or flipped, the clamped corners meet or cross.
    if right <= left or bottom <= top:
        return None
    return BBox(
        x=left,
        y=top,
        width=round(right - left, RATIO_DIGITS),
        height=round(bottom - top, RATIO_DIGITS),
    )


def to_detections(result: Any, width: int, height: int) -> list[Detection]:
    """Convert one Ultralytics result into detections, best first, with ratio boxes."""
    boxes = result.boxes
    rows = zip(boxes.xyxy.tolist(), boxes.conf.tolist(), boxes.cls.tolist(), strict=True)
    found: list[tuple[float, int, BBox]] = []
    for (x1, y1, x2, y2), confidence, class_id in rows:
        bbox = ratio_box(x1, y1, x2, y2, width, height)
        if bbox is not None:
            found.append((confidence, int(class_id), bbox))
    found.sort(key=lambda item: item[0], reverse=True)
    return [
        Detection(
            id=f"d{rank}",
            label=result.names[class_id],
            label_arabic=arabic_label(result.names[class_id]),
            confidence=round(confidence, RATIO_DIGITS),
            bbox=bbox,
        )
        for rank, (confidence, class_id, bbox) in enumerate(found, start=1)
    ]


def load_ultralytics_model(family: ModelFamily, checkpoint: Path) -> Any:
    """Build a YOLOE or YOLO-World model from a checkpoint inside the weights directory."""
    configure_ultralytics(checkpoint.parent)
    ultralytics = importlib.import_module("ultralytics")
    model_class = ultralytics.YOLOE if family is ModelFamily.YOLOE else ultralytics.YOLOWorld
    return model_class(str(checkpoint))


def _builtin_names(model: Any) -> list[str]:
    """Return the class names a checkpoint ships with, in class order."""
    return [str(name) for _, name in sorted(model.names.items())]


class UltralyticsDetector:
    """
    YOLOE or YOLO-World through Ultralytics, with the vocabulary set per request.

    The text encoder turns a vocabulary into the model's classes; doing it costs a
    second or two, so the last vocabulary is kept and reused. Without the encoder, a
    YOLO-World checkpoint falls back to the 80 COCO classes it ships with (`coco`
    mode). A YOLOE checkpoint ships none (its class names are "0", "1", ... and it
    finds nothing until it is given a vocabulary), so it is unavailable.
    """

    def __init__(self, settings: Settings, loader: ModelLoader = load_ultralytics_model) -> None:
        self._family = family_of(settings.detector_model)
        self._weights_dir = settings.vision_weights_dir
        self._checkpoint = self._weights_dir / settings.detector_model
        self._device = settings.detector_device
        self._loader = loader
        # Ultralytics predictors are not thread-safe; requests are served one at a time.
        self._lock = threading.Lock()
        self._model: Any | None = None
        self._mode = VocabularyMode.UNLOADED
        self._active: tuple[str, ...] = ()
        self._builtin: list[str] = []
        self._builtin_intact = True  # false once the head was given another vocabulary
        self._encoder_failed = False
        self._load_error: str | None = None

    def warmup(self) -> None:
        """Load the model, encode the default vocabulary and run one inference."""
        blank = Image.new("RGB", (64, 64), (127, 127, 127))
        self.detect(blank, DEFAULT_VOCABULARY, conf=0.9, max_detections=1)

    def status(self) -> DetectorStatus:
        """Describe the detector without taking the inference lock."""
        if self._model is not None:
            error = None
        elif self._checkpoint.is_file():
            error = self._load_error
        else:
            error = self._missing_message()
        if error is None and not self._has_fallback and not self._can_encode():
            error = self._encoder_message()
        if self._mode is VocabularyMode.OPEN:
            size = len(self._active)
        elif self._mode is VocabularyMode.COCO:
            size = len(self._builtin)
        else:
            size = 0
        return DetectorStatus(
            name=self._family.value,
            model=self._checkpoint.stem,
            device=self._device,
            loaded=self._model is not None,
            vocabulary_size=size,
            vocabulary_mode=self._mode,
            error=error,
        )

    def detect(
        self,
        image: Image.Image,
        vocabulary: Sequence[str],
        conf: float,
        max_detections: int,
    ) -> DetectionResult:
        """Find the objects of `vocabulary` in an RGB image."""
        with self._lock:
            started = time.perf_counter()
            model = self._load()
            self._apply_vocabulary(model, tuple(vocabulary))
            result = model.predict(
                image, conf=conf, max_det=max_detections, device=self._device, verbose=False
            )[0]
            detections = to_detections(result, image.width, image.height)
            ms = round((time.perf_counter() - started) * 1000)
            mode = self._mode
        logger.info(
            "%s found %d objects in %d ms (%s vocabulary, conf %.2f)",
            self._checkpoint.stem,
            len(detections),
            ms,
            mode.value,
            conf,
        )
        return DetectionResult(
            detections=detections, model=self._checkpoint.stem, ms=ms, vocabulary_mode=mode
        )

    @property
    def _has_fallback(self) -> bool:
        """Only a YOLO-World checkpoint carries class names of its own (COCO)."""
        return self._family is ModelFamily.YOLO_WORLD

    def _missing_message(self) -> str:
        return f"{self._checkpoint.name} is missing; run scripts/fetch-weights.sh"

    def _encoder_message(self) -> str:
        files = ", ".join(ENCODER_FILES[self._family])
        return f"The text encoder ({files}) is missing or unusable; run scripts/fetch-weights.sh"

    def _load(self) -> Any:
        """Return the model, loading it the first time. Called with the lock held."""
        if self._model is not None:
            return self._model
        if not self._checkpoint.is_file():
            raise DetectorUnavailableError(self._missing_message())
        started = time.perf_counter()
        try:
            model = self._loader(self._family, self._checkpoint)
        except Exception as exc:  # torch and zipfile fail in many ways on a damaged file
            self._load_error = f"{self._checkpoint.name} could not be loaded ({type(exc).__name__})"
            logger.exception("loading %s failed", self._checkpoint)
            raise DetectorUnavailableError(self._load_error) from exc
        self._load_error = None
        self._builtin = _builtin_names(model) if self._has_fallback else []
        self._model = model
        logger.info(
            "loaded %s on %s in %d ms (%d built-in classes)",
            self._checkpoint.name,
            self._device,
            (time.perf_counter() - started) * 1000,
            len(self._builtin),
        )
        return model

    def _can_encode(self) -> bool:
        return not self._encoder_failed and encoder_ready(self._family, self._weights_dir)

    def _apply_vocabulary(self, model: Any, wanted: tuple[str, ...]) -> None:
        """Make the model score against `wanted`, or against COCO when it cannot."""
        if self._mode is VocabularyMode.OPEN and wanted == self._active:
            return
        if self._can_encode():
            try:
                self._set_classes(model, list(wanted))
            except Exception:  # the encoder file may be damaged or from another version
                self._encoder_failed = True
                logger.exception("encoding %d labels failed", len(wanted))
            else:
                self._active = wanted
                self._mode = VocabularyMode.OPEN
                self._builtin_intact = False
                return
        self._use_builtin_names()

    def _set_classes(self, model: Any, labels: list[str]) -> None:
        if self._family is ModelFamily.YOLOE:
            model.set_classes(labels, model.get_text_pe(labels))
        else:
            model.set_classes(labels)

    def _use_builtin_names(self) -> None:
        if not self._has_fallback or not self._builtin_intact:
            raise DetectorUnavailableError(self._encoder_message())
        if self._mode is not VocabularyMode.COCO:
            logger.warning(
                "text encoder unavailable; detecting the %d COCO classes", len(self._builtin)
            )
        self._mode = VocabularyMode.COCO
