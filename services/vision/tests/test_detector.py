from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from tests.conftest import COCO_NAMES, FakeModel, FakeTensor
from vision.config import ModelFamily, Settings
from vision.detector import (
    UltralyticsDetector,
    load_ultralytics_model,
    ratio_box,
    to_detections,
)
from vision.errors import DetectorUnavailableError
from vision.schemas import BBox, VocabularyMode
from vision.vocabulary import DEFAULT_VOCABULARY

YOLOE_ENCODER = "mobileclip_blt.ts"
WORLD_ENCODER = "clip/ViT-B-32.pt"
WORLD_MODEL = "yolov8s-worldv2.pt"


def result_of(
    rows: list[tuple[float, float, float, float, float, int]],
    names: dict[int, str] | None = None,
) -> Any:
    boxes = SimpleNamespace(
        xyxy=FakeTensor([list(row[:4]) for row in rows]),
        conf=FakeTensor([row[4] for row in rows]),
        cls=FakeTensor([float(row[5]) for row in rows]),
    )
    return SimpleNamespace(boxes=boxes, names=names or COCO_NAMES)


# ---------------------------------------------------------------- ratio_box


def test_ratio_box_converts_pixels_to_ratios_of_the_image() -> None:
    assert ratio_box(10, 20, 50, 40, 100, 200) == BBox(x=0.1, y=0.1, width=0.4, height=0.1)


@pytest.mark.parametrize(
    ("box", "expected"),
    [
        ((-10, -10, 50, 50), BBox(x=0, y=0, width=0.5, height=0.5)),
        ((50, 50, 150, 150), BBox(x=0.5, y=0.5, width=0.5, height=0.5)),
        ((-20, -20, 120, 120), BBox(x=0, y=0, width=1, height=1)),
    ],
)
def test_ratio_box_clamps_a_box_that_crosses_the_border(
    box: tuple[float, float, float, float], expected: BBox
) -> None:
    assert ratio_box(*box, 100, 100) == expected


@pytest.mark.parametrize(
    "box",
    [
        (-50, -50, -10, -10),  # left of and above the image
        (110, 10, 150, 50),  # right of it
        (10, 110, 50, 150),  # below it
        (-50, 10, 0, 50),  # touching the left edge from outside
        (100, 10, 150, 50),  # touching the right edge from outside
        (10, 10, 10, 50),  # no width
        (10, 10, 50, 10),  # no height
        (50, 10, 10, 50),  # flipped
        (10, 10, 10.001, 50),  # less than a rounding step wide
    ],
)
def test_ratio_box_drops_a_box_outside_the_image(box: tuple[float, float, float, float]) -> None:
    assert ratio_box(*box, 100, 100) is None


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_ratio_box_drops_a_box_with_a_non_finite_corner(bad: float) -> None:
    assert ratio_box(10, 10, bad, 50, 100, 100) is None


def test_ratio_box_never_leaves_the_image_after_rounding() -> None:
    bbox = ratio_box(0.00004, 0.00004, 99.99996, 99.99996, 100, 100)

    assert bbox is not None
    assert bbox.x + bbox.width <= 1
    assert bbox.y + bbox.height <= 1


# ---------------------------------------------------------------- to_detections


def test_to_detections_sorts_by_confidence_and_numbers_the_survivors() -> None:
    result = result_of(
        [
            (10, 10, 50, 50, 0.4, 0),  # person
            (500, 500, 600, 600, 0.99, 1),  # outside a 100x100 image: dropped
            (20, 20, 80, 80, 0.8, 2),  # car
        ]
    )

    detections = to_detections(result, 100, 100)

    assert [(d.id, d.label, d.confidence) for d in detections] == [
        ("d1", "car", 0.8),
        ("d2", "person", 0.4),
    ]
    assert detections[0].bbox == BBox(x=0.2, y=0.2, width=0.6, height=0.6)


def test_to_detections_adds_arabic_only_when_known() -> None:
    result = result_of([(0, 0, 10, 10, 0.5, 0), (0, 0, 10, 10, 0.4, 1)], {0: "olive", 1: "sextant"})

    detections = to_detections(result, 100, 100)

    assert [d.label_arabic for d in detections] == ["زيتون", None]


def test_to_detections_rounds_confidence_and_handles_no_boxes() -> None:
    assert to_detections(result_of([(0, 0, 10, 10, 0.123456, 0)]), 100, 100)[0].confidence == 0.1235
    assert to_detections(result_of([]), 100, 100) == []


# ---------------------------------------------------------------- UltralyticsDetector


class Loader:
    """A loader that hands out one fake model and counts how often it was asked."""

    def __init__(self, model: FakeModel | None = None, error: Exception | None = None) -> None:
        self.model = model or FakeModel()
        self.error = error
        self.calls: list[tuple[ModelFamily, Path]] = []

    def __call__(self, family: ModelFamily, checkpoint: Path) -> FakeModel:
        self.calls.append((family, checkpoint))
        if self.error is not None:
            raise self.error
        return self.model


def install(settings: Settings, *encoder_files: str) -> None:
    """Put a checkpoint, and the named encoder files, where the detector looks."""
    (settings.vision_weights_dir / settings.detector_model).write_bytes(b"weights")
    for name in encoder_files:
        path = settings.vision_weights_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"encoder")


@pytest.fixture
def world_settings(weights_dir: Path) -> Settings:
    return Settings(
        _env_file=None,
        vision_weights_dir=weights_dir,
        vision_warmup=False,
        detector_model=WORLD_MODEL,
    )


def image(size: tuple[int, int] = (200, 100)) -> Image.Image:
    return Image.new("RGB", size, "white")


def test_nothing_is_loaded_until_the_first_detection(settings: Settings) -> None:
    install(settings, YOLOE_ENCODER)
    loader = Loader()

    detector = UltralyticsDetector(settings, loader)
    status = detector.status()

    assert loader.calls == []
    assert (status.name, status.model, status.device) == ("yoloe", "yoloe-11s-seg", "cpu")
    assert (status.loaded, status.vocabulary_size) == (False, 0)
    assert status.vocabulary_mode is VocabularyMode.UNLOADED
    assert status.error is None


def test_detect_returns_ratio_boxes_of_the_received_image(settings: Settings) -> None:
    install(settings, YOLOE_ENCODER)
    model = FakeModel(rows=[(20, 10, 120, 60, 0.9, 1)])
    detector = UltralyticsDetector(settings, Loader(model))

    result = detector.detect(image((200, 100)), ["person", "olive"], 0.3, 7)

    assert model.received_sizes == [(200, 100)]
    (detection,) = result.detections
    assert (detection.label, detection.label_arabic) == ("olive", "زيتون")
    assert detection.bbox == BBox(x=0.1, y=0.1, width=0.5, height=0.5)
    assert (result.model, result.vocabulary_mode) == ("yoloe-11s-seg", VocabularyMode.OPEN)
    assert result.ms >= 0


def test_detect_passes_the_request_to_the_model(settings: Settings) -> None:
    install(settings, YOLOE_ENCODER)
    model = FakeModel()
    detector = UltralyticsDetector(settings, Loader(model))

    detector.detect(image(), ["cup"], 0.35, 11)

    assert (
        "predict",
        {"conf": 0.35, "max_det": 11, "device": "cpu", "verbose": False},
    ) in model.calls


def test_yoloe_gets_its_text_embeddings(settings: Settings) -> None:
    install(settings, YOLOE_ENCODER)
    model = FakeModel()
    detector = UltralyticsDetector(settings, Loader(model))

    detector.detect(image(), ["cup", "plate"], 0.2, 20)

    assert ("get_text_pe", ["cup", "plate"]) in model.calls
    assert ("set_classes", (["cup", "plate"], "embeddings")) in model.calls


def test_yolo_world_sets_classes_without_embeddings(world_settings: Settings) -> None:
    install(world_settings, WORLD_ENCODER)
    model = FakeModel(names=COCO_NAMES)
    detector = UltralyticsDetector(world_settings, Loader(model))

    detector.detect(image(), ["cup"], 0.2, 20)

    assert ("set_classes", (["cup"], None)) in model.calls
    assert model.count("get_text_pe") == 0


def test_the_model_is_loaded_once_and_the_vocabulary_only_when_it_changes(
    settings: Settings,
) -> None:
    install(settings, YOLOE_ENCODER)
    loader = Loader()
    detector = UltralyticsDetector(settings, loader)

    detector.detect(image(), ["cup"], 0.2, 20)
    detector.detect(image(), ["cup"], 0.2, 20)
    detector.detect(image(), ["plate"], 0.2, 20)
    detector.detect(image(), ["plate"], 0.2, 20)

    assert len(loader.calls) == 1
    assert loader.model.count("set_classes") == 2
    assert loader.model.count("predict") == 4
    status = detector.status()
    assert (status.loaded, status.vocabulary_size, status.error) == (True, 1, None)
    assert status.vocabulary_mode is VocabularyMode.OPEN


def test_warmup_loads_the_model_and_encodes_the_default_vocabulary(settings: Settings) -> None:
    install(settings, YOLOE_ENCODER)
    loader = Loader()
    detector = UltralyticsDetector(settings, loader)

    detector.warmup()

    assert detector.status().loaded
    assert detector.status().vocabulary_size == len(DEFAULT_VOCABULARY)
    assert ("set_classes", (list(DEFAULT_VOCABULARY), "embeddings")) in loader.model.calls
    assert loader.model.received_sizes == [(64, 64)]


def test_missing_weights_make_the_detector_unavailable(settings: Settings) -> None:
    detector = UltralyticsDetector(settings, Loader())

    status = detector.status()
    with pytest.raises(DetectorUnavailableError) as caught:
        detector.detect(image(), ["cup"], 0.2, 20)

    assert status.error is not None
    assert "yoloe-11s-seg.pt is missing" in status.error
    assert (caught.value.status, caught.value.code) == (503, "detector_unavailable")
    assert "fetch-weights.sh" in caught.value.detail


def test_a_damaged_checkpoint_is_reported_and_retried(settings: Settings) -> None:
    install(settings, YOLOE_ENCODER)
    loader = Loader(error=RuntimeError("PytorchStreamReader failed"))
    detector = UltralyticsDetector(settings, loader)

    with pytest.raises(DetectorUnavailableError, match="could not be loaded"):
        detector.detect(image(), ["cup"], 0.2, 20)
    assert detector.status().error == "yoloe-11s-seg.pt could not be loaded (RuntimeError)"
    assert not detector.status().loaded

    loader.error = None  # the file was fixed
    detector.detect(image(), ["cup"], 0.2, 20)

    assert detector.status().loaded
    assert detector.status().error is None


def test_yoloe_without_its_text_encoder_is_unavailable(settings: Settings) -> None:
    install(settings)
    model = FakeModel()
    detector = UltralyticsDetector(settings, Loader(model))

    with pytest.raises(DetectorUnavailableError, match=r"mobileclip_blt\.ts"):
        detector.detect(image(), ["cup"], 0.2, 20)

    assert model.count("set_classes") == 0
    assert model.count("predict") == 0
    assert detector.status().error is not None


def test_yoloe_status_names_the_missing_encoder_before_any_request(settings: Settings) -> None:
    install(settings)

    status = UltralyticsDetector(settings, Loader()).status()

    assert status.error is not None
    assert "mobileclip_blt.ts" in status.error


def test_yolo_world_without_its_text_encoder_falls_back_to_coco(world_settings: Settings) -> None:
    install(world_settings)
    model = FakeModel(names=COCO_NAMES, rows=[(0, 0, 50, 50, 0.9, 2)])
    detector = UltralyticsDetector(world_settings, Loader(model))

    result = detector.detect(image(), ["cup", "plate"], 0.2, 20)
    detector.detect(image(), ["cup", "plate"], 0.2, 20)

    assert result.vocabulary_mode is VocabularyMode.COCO
    assert [d.label for d in result.detections] == ["car"]
    assert model.count("set_classes") == 0
    status = detector.status()
    assert (status.vocabulary_mode, status.vocabulary_size, status.error) == (
        VocabularyMode.COCO,
        len(COCO_NAMES),
        None,
    )


def test_the_encoder_is_picked_up_once_it_is_installed(world_settings: Settings) -> None:
    install(world_settings)
    model = FakeModel(names=COCO_NAMES)
    detector = UltralyticsDetector(world_settings, Loader(model))
    assert detector.detect(image(), ["cup"], 0.2, 20).vocabulary_mode is VocabularyMode.COCO

    install(world_settings, WORLD_ENCODER)
    result = detector.detect(image(), ["cup"], 0.2, 20)

    assert result.vocabulary_mode is VocabularyMode.OPEN
    assert model.count("set_classes") == 1


def test_an_encoder_that_fails_falls_back_to_coco_and_is_not_retried(
    world_settings: Settings,
) -> None:
    install(world_settings, WORLD_ENCODER)
    model = FakeModel(names=COCO_NAMES, set_classes_error=OSError("bad file"))
    detector = UltralyticsDetector(world_settings, Loader(model))

    first = detector.detect(image(), ["cup"], 0.2, 20)
    second = detector.detect(image(), ["plate"], 0.2, 20)

    assert first.vocabulary_mode is second.vocabulary_mode is VocabularyMode.COCO
    assert model.count("set_classes") == 1


def test_an_encoder_that_fails_after_working_keeps_the_last_vocabulary_or_gives_up(
    world_settings: Settings,
) -> None:
    install(world_settings, WORLD_ENCODER)
    model = FakeModel(names=COCO_NAMES)
    detector = UltralyticsDetector(world_settings, Loader(model))
    detector.detect(image(), ["cup"], 0.2, 20)

    model.set_classes_error = OSError("bad file")
    with pytest.raises(DetectorUnavailableError, match="text encoder"):
        detector.detect(image(), ["plate"], 0.2, 20)

    # The vocabulary that is already encoded still works.
    assert detector.detect(image(), ["cup"], 0.2, 20).vocabulary_mode is VocabularyMode.OPEN


def test_yoloe_with_a_failing_encoder_is_unavailable(settings: Settings) -> None:
    install(settings, YOLOE_ENCODER)
    model = FakeModel(set_classes_error=OSError("bad file"))
    detector = UltralyticsDetector(settings, Loader(model))

    with pytest.raises(DetectorUnavailableError):
        detector.detect(image(), ["cup"], 0.2, 20)

    assert detector.status().error is not None


# ---------------------------------------------------------------- the real loader


def test_load_ultralytics_model_builds_the_model_of_the_family(
    monkeypatch: pytest.MonkeyPatch, weights_dir: Path
) -> None:
    configured: list[Path] = []
    fake = SimpleNamespace(
        YOLOE=lambda path: ("yoloe", path),
        YOLOWorld=lambda path: ("world", path),
    )
    monkeypatch.setattr("vision.detector.configure_ultralytics", configured.append)
    monkeypatch.setattr("vision.detector.importlib.import_module", lambda name: fake)
    checkpoint = weights_dir / "model.pt"

    assert load_ultralytics_model(ModelFamily.YOLOE, checkpoint) == ("yoloe", str(checkpoint))
    assert load_ultralytics_model(ModelFamily.YOLO_WORLD, checkpoint) == ("world", str(checkpoint))
    assert configured == [weights_dir, weights_dir]
