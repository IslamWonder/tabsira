from __future__ import annotations

import base64
import logging
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from starlette.formparsers import MultiPartParser

from tests.conftest import FakeModel, image_bytes
from vision import main
from vision.config import Settings
from vision.detector import (
    DetectionResult,
    Detector,
    DetectorStatus,
    UltralyticsDetector,
)
from vision.errors import DetectorUnavailableError
from vision.schemas import BBox, Detection, VocabularyMode
from vision.vocabulary import DEFAULT_VOCABULARY

DETECTION = Detection(
    id="d1",
    label="olive",
    label_arabic="زيتون",
    confidence=0.91,
    bbox=BBox(x=0.1, y=0.2, width=0.3, height=0.4),
)


class FakeDetector:
    """A detector that records its calls and returns what the test set up."""

    def __init__(self) -> None:
        self.calls: list[tuple[Image.Image, list[str], float, int]] = []
        self.warmups = 0
        self.warmup_error: Exception | None = None
        self.detect_error: Exception | None = None
        self.state = DetectorStatus(
            name="yoloe",
            model="yoloe-11s-seg",
            device="cpu",
            loaded=True,
            vocabulary_size=114,
            vocabulary_mode=VocabularyMode.OPEN,
            error=None,
        )

    def warmup(self) -> None:
        self.warmups += 1
        if self.warmup_error is not None:
            raise self.warmup_error

    def status(self) -> DetectorStatus:
        return self.state

    def detect(
        self, image: Image.Image, vocabulary: Sequence[str], conf: float, max_detections: int
    ) -> DetectionResult:
        if self.detect_error is not None:
            raise self.detect_error
        self.calls.append((image, list(vocabulary), conf, max_detections))
        return DetectionResult(
            detections=[DETECTION],
            model="yoloe-11s-seg",
            ms=42,
            vocabulary_mode=VocabularyMode.OPEN,
        )


@pytest.fixture
def detector() -> FakeDetector:
    return FakeDetector()


@pytest.fixture
def client(settings: Settings, detector: FakeDetector) -> Iterator[TestClient]:
    with TestClient(main.create_app(settings, detector), raise_server_exceptions=False) as client:
        yield client


def upload(client: TestClient, data: bytes | None = None, /, **fields: Any) -> Any:
    return client.post(
        "/detect",
        files={"image": ("photo.png", data if data is not None else image_bytes(), "image/png")},
        data=fields,
    )


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# ---------------------------------------------------------------- /health


def test_health_when_the_detector_is_loaded(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "detector": "yoloe",
        "model": "yoloe-11s-seg",
        "device": "cpu",
        "modelLoaded": True,
        "vocabularySize": 114,
        "vocabularyMode": "open",
        "error": None,
        "reranker": "BAAI/bge-reranker-v2-m3",
        "rerankerLoaded": False,
        "rerankerError": (
            "the weights of BAAI/bge-reranker-v2-m3 are missing; run scripts/fetch-weights.sh"
        ),
    }


def test_health_when_the_model_is_not_loaded_yet(
    client: TestClient, detector: FakeDetector
) -> None:
    detector.state = DetectorStatus(
        "yoloe", "yoloe-11s-seg", "cpu", False, 0, VocabularyMode.UNLOADED, None
    )

    body = client.get("/health").json()

    assert (body["ok"], body["modelLoaded"], body["vocabularyMode"]) == (True, False, "unloaded")


def test_health_when_the_detector_cannot_work(client: TestClient, detector: FakeDetector) -> None:
    detector.state = DetectorStatus(
        "yoloe",
        "yoloe-11s-seg",
        "cpu",
        False,
        0,
        VocabularyMode.UNLOADED,
        "yoloe-11s-seg.pt is missing",
    )

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["error"] == "yoloe-11s-seg.pt is missing"


def test_health_in_coco_mode(client: TestClient, detector: FakeDetector) -> None:
    detector.state = DetectorStatus(
        "yolo-world", "yolov8s-worldv2", "cpu", True, 80, VocabularyMode.COCO, None
    )

    body = client.get("/health").json()

    assert (body["ok"], body["vocabularySize"], body["vocabularyMode"]) == (True, 80, "coco")


# ---------------------------------------------------------------- /detect


def test_detect_returns_detections_in_the_documented_shape(
    client: TestClient, detector: FakeDetector
) -> None:
    response = upload(
        client, image_bytes((60, 30)), vocabulary="Olive, tree", conf="0.4", max_detections="5"
    )

    assert response.status_code == 200
    assert response.json() == {
        "detections": [
            {
                "id": "d1",
                "label": "olive",
                "labelArabic": "زيتون",
                "confidence": 0.91,
                "bbox": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
            }
        ],
        "width": 60,
        "height": 30,
        "model": "yoloe-11s-seg",
        "ms": 42,
        "vocabularyMode": "open",
    }
    (_, labels, conf, max_detections) = detector.calls[0]
    assert (labels, conf, max_detections) == (["olive", "tree"], 0.4, 5)


def test_detect_uses_the_defaults_of_the_settings(
    weights_dir: Path, detector: FakeDetector
) -> None:
    settings = Settings(
        _env_file=None,
        vision_weights_dir=weights_dir,
        vision_warmup=False,
        detector_conf=0.33,
        detector_max_detections=9,
    )
    with TestClient(main.create_app(settings, detector)) as client:
        assert upload(client).status_code == 200

    (_, labels, conf, max_detections) = detector.calls[0]
    assert (labels, conf, max_detections) == (list(DEFAULT_VOCABULARY), 0.33, 9)


def test_detect_refuses_what_is_not_an_image(client: TestClient) -> None:
    response = upload(client, b"just some text")

    assert response.status_code == 415
    assert response.json()["error"] == "unsupported_media_type"
    assert set(response.json()) == {"error", "detail"}


def test_detect_refuses_an_empty_upload(client: TestClient) -> None:
    response = upload(client, b"")

    assert (response.status_code, response.json()["error"]) == (400, "empty_image")


def test_detect_refuses_an_image_over_the_byte_limit(
    weights_dir: Path, detector: FakeDetector
) -> None:
    settings = Settings(
        _env_file=None,
        vision_weights_dir=weights_dir,
        vision_warmup=False,
        vision_max_image_bytes=100,
    )
    with TestClient(main.create_app(settings, detector)) as client:
        response = upload(client, image_bytes((200, 200)))

    assert (response.status_code, response.json()["error"]) == (413, "image_too_large")
    assert detector.calls == []


def test_detect_refuses_an_image_over_the_pixel_limit(
    weights_dir: Path, detector: FakeDetector
) -> None:
    settings = Settings(
        _env_file=None,
        vision_weights_dir=weights_dir,
        vision_warmup=False,
        vision_max_image_pixels=100,
    )
    with TestClient(main.create_app(settings, detector)) as client:
        response = upload(client, image_bytes((20, 20)))

    assert (response.status_code, response.json()["error"]) == (413, "image_too_large")


def test_a_huge_body_is_refused_before_it_is_read(
    weights_dir: Path, detector: FakeDetector
) -> None:
    settings = Settings(
        _env_file=None,
        vision_weights_dir=weights_dir,
        vision_warmup=False,
        vision_max_image_bytes=1000,
    )
    with TestClient(main.create_app(settings, detector)) as client:
        response = client.post("/detect-json", content=b"x" * 100_000)

    assert (response.status_code, response.json()["error"]) == (413, "image_too_large")


@pytest.mark.parametrize(
    "fields",
    [
        {"conf": "1.5"},
        {"conf": "-0.1"},
        {"max_detections": "0"},
        {"max_detections": "301"},
        {"conf": "high"},
    ],
)
def test_detect_validates_its_parameters(client: TestClient, fields: dict[str, str]) -> None:
    response = upload(client, **fields)

    assert (response.status_code, response.json()["error"]) == (422, "invalid_request")
    assert next(iter(fields)) in response.json()["detail"]


def test_detect_needs_an_image_field(client: TestClient) -> None:
    response = client.post("/detect", data={"conf": "0.2"})

    assert (response.status_code, response.json()["error"]) == (422, "invalid_request")
    assert "image" in response.json()["detail"]


def test_detect_refuses_a_vocabulary_that_is_too_large(client: TestClient) -> None:
    labels = ",".join(f"label {number}" for number in range(501))

    response = upload(client, vocabulary=labels)

    assert (response.status_code, response.json()["error"]) == (422, "vocabulary_too_large")


def test_detect_accepts_the_largest_vocabulary(client: TestClient) -> None:
    labels = ",".join(f"label {number}" for number in range(500))

    assert upload(client, vocabulary=labels).status_code == 200


# ---------------------------------------------------------------- /detect-json


def test_detect_json_accepts_bare_base64_and_data_urls(
    client: TestClient, detector: FakeDetector
) -> None:
    encoded = b64(image_bytes((50, 25)))
    wrapped = "\n".join(encoded[i : i + 20] for i in range(0, len(encoded), 20))

    plain = client.post("/detect-json", json={"imageBase64": encoded})
    data_url = client.post("/detect-json", json={"imageBase64": f"data:image/png;base64,{encoded}"})
    lines = client.post("/detect-json", json={"imageBase64": wrapped})

    assert [r.status_code for r in (plain, data_url, lines)] == [200, 200, 200]
    assert plain.json()["width"] == data_url.json()["width"] == lines.json()["width"] == 50
    assert len(detector.calls) == 3


def test_detect_json_takes_the_vocabulary_as_a_list_or_a_string(
    client: TestClient, detector: FakeDetector
) -> None:
    encoded = b64(image_bytes())

    client.post("/detect-json", json={"imageBase64": encoded, "vocabulary": ["Cup", "plate"]})
    client.post(
        "/detect-json",
        json={"imageBase64": encoded, "vocabulary": "bowl, spoon", "conf": 0.5, "maxDetections": 3},
    )

    assert detector.calls[0][1] == ["cup", "plate"]
    assert (detector.calls[1][1], detector.calls[1][2], detector.calls[1][3]) == (
        ["bowl", "spoon"],
        0.5,
        3,
    )


def test_detect_json_refuses_invalid_base64(client: TestClient) -> None:
    response = client.post("/detect-json", json={"imageBase64": "this is not base64!"})

    assert (response.status_code, response.json()["error"]) == (400, "invalid_base64")


def test_detect_json_refuses_base64_of_something_that_is_not_an_image(client: TestClient) -> None:
    response = client.post("/detect-json", json={"imageBase64": b64(b"hello world")})

    assert (response.status_code, response.json()["error"]) == (415, "unsupported_media_type")


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({}, "imageBase64"),
        ({"imageBase64": ""}, "imageBase64"),
        ({"imageBase64": "AAAA", "conf": 2}, "conf"),
        ({"imageBase64": "AAAA", "maxDetections": 0}, "maxDetections"),
    ],
)
def test_detect_json_validates_its_body(
    client: TestClient, body: dict[str, Any], field: str
) -> None:
    response = client.post("/detect-json", json=body)

    assert (response.status_code, response.json()["error"]) == (422, "invalid_request")
    assert field in response.json()["detail"]


# ---------------------------------------------------------------- errors


def test_an_unavailable_detector_is_a_503(client: TestClient, detector: FakeDetector) -> None:
    detector.detect_error = DetectorUnavailableError(
        "yoloe-11s-seg.pt is missing; run scripts/fetch-weights.sh"
    )

    response = upload(client)

    assert response.status_code == 503
    assert response.json() == {
        "error": "detector_unavailable",
        "detail": "yoloe-11s-seg.pt is missing; run scripts/fetch-weights.sh",
    }


def test_an_unexpected_failure_is_a_500_that_leaks_nothing(
    client: TestClient, detector: FakeDetector
) -> None:
    detector.detect_error = RuntimeError("secret internal path /srv/x")

    response = upload(client)

    assert response.status_code == 500
    assert response.json() == {
        "error": "internal_error",
        "detail": "The detection failed unexpectedly.",
    }


def test_framework_errors_have_the_same_shape(client: TestClient) -> None:
    missing = client.get("/nope")
    wrong_method = client.get("/detect")

    assert (missing.status_code, missing.json()) == (
        404,
        {"error": "http_error", "detail": "Not Found"},
    )
    assert wrong_method.status_code == 405
    assert wrong_method.json()["error"] == "http_error"


# ---------------------------------------------------------------- start-up


def test_warmup_runs_at_startup_when_enabled(weights_dir: Path, detector: FakeDetector) -> None:
    settings = Settings(_env_file=None, vision_weights_dir=weights_dir, vision_warmup=True)

    with TestClient(main.create_app(settings, detector)) as client:
        assert client.get("/health").status_code == 200

    assert detector.warmups == 1


def test_a_failed_warmup_does_not_stop_the_service(
    weights_dir: Path, detector: FakeDetector, caplog: pytest.LogCaptureFixture
) -> None:
    settings = Settings(_env_file=None, vision_weights_dir=weights_dir, vision_warmup=True)
    detector.warmup_error = DetectorUnavailableError("weights are missing")

    with (
        caplog.at_level(logging.WARNING, logger="vision"),
        TestClient(main.create_app(settings, detector)) as client,
    ):
        assert client.get("/health").status_code == 200

    assert "warm-up skipped: weights are missing" in caplog.text


def test_no_warmup_when_disabled(client: TestClient, detector: FakeDetector) -> None:
    assert client.get("/health").status_code == 200
    assert detector.warmups == 0


def test_the_service_builds_its_own_detector_and_reports_missing_weights(
    settings: Settings,
) -> None:
    with TestClient(main.create_app(settings)) as client:
        body = client.get("/health").json()
        refused = upload(client)

    assert (body["ok"], body["modelLoaded"], body["model"]) == (False, False, "yoloe-11s-seg")
    assert "is missing" in body["error"]
    assert (refused.status_code, refused.json()["error"]) == (503, "detector_unavailable")


def test_the_service_reads_its_settings_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, weights_dir: Path
) -> None:
    monkeypatch.setenv("VISION_WEIGHTS_DIR", str(weights_dir))
    monkeypatch.setenv("VISION_WARMUP", "false")
    monkeypatch.setenv("DETECTOR_MODEL", "yolov8s-worldv2.pt")

    with TestClient(main.create_app()) as client:
        body = client.get("/health").json()

    assert (body["detector"], body["model"]) == ("yolo-world", "yolov8s-worldv2")


def test_uploads_stay_in_memory_up_to_the_accepted_size(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, detector: FakeDetector
) -> None:
    monkeypatch.setattr(
        MultiPartParser, "spool_max_size", 1024 * 1024
    )  # Starlette's default; restored afterwards

    main.create_app(settings, detector)

    assert MultiPartParser.spool_max_size > settings.vision_max_image_bytes


def test_configure_logging_adds_one_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main.logger, "handlers", [])

    main.configure_logging()
    main.configure_logging()

    assert len(main.logger.handlers) == 1


def test_run_serves_the_app_factory_on_the_configured_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    served: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(
        "vision.main.uvicorn.run", lambda *args, **kwargs: served.append((args, kwargs))
    )
    monkeypatch.setenv("VISION_PORT", "8123")

    main.run()

    assert served == [
        (("vision.main:create_app",), {"factory": True, "host": "127.0.0.1", "port": 8123})
    ]


# ---------------------------------------------------------------- the whole path


def test_boxes_are_ratios_of_the_image_after_its_orientation_is_applied(
    settings: Settings, weights_dir: Path
) -> None:
    # A 40x20 photo stored sideways (EXIF orientation 6) is shown, and detected, as 20x40.
    (weights_dir / settings.detector_model).write_bytes(b"weights")
    (weights_dir / "mobileclip_blt.ts").write_bytes(b"encoder")
    model = FakeModel(rows=[(2, 4, 12, 24, 0.9, 0), (50, 50, 60, 60, 0.95, 0)])
    real: Detector = UltralyticsDetector(settings, lambda _family, _path: model)

    with TestClient(main.create_app(settings, real)) as client:
        response = upload(client, image_bytes((40, 20), "JPEG", orientation=6), vocabulary="olive")

    assert model.received_sizes == [(20, 40)]
    body = response.json()
    assert (body["width"], body["height"]) == (20, 40)
    assert [d["label"] for d in body["detections"]] == [
        "olive"
    ]  # the box outside the image is gone
    assert body["detections"][0]["bbox"] == {"x": 0.1, "y": 0.1, "width": 0.5, "height": 0.5}
    assert body["vocabularyMode"] == "open"
