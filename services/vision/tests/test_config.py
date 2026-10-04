from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from vision.config import SERVICE_DIR, ModelFamily, Settings, family_of


def test_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.vision_host == "127.0.0.1"
    assert settings.vision_port == 8100
    assert settings.vision_weights_dir == SERVICE_DIR / "weights"
    assert settings.vision_max_image_bytes == 15 * 1024 * 1024
    assert settings.vision_max_image_pixels == 40_000_000
    assert settings.vision_warmup is True
    assert settings.detector_model == "yoloe-11s-seg.pt"
    assert settings.detector_device == "cpu"
    assert settings.detector_conf == 0.2
    assert settings.detector_max_detections == 20


def test_environment_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DETECTOR_MODEL", "yolov8s-worldv2.pt")
    monkeypatch.setenv("VISION_PORT", "8200")
    monkeypatch.setenv("VISION_WARMUP", "false")

    settings = Settings(_env_file=None)

    assert settings.detector_model == "yolov8s-worldv2.pt"
    assert settings.vision_port == 8200
    assert settings.vision_warmup is False


def test_root_env_file_is_read_and_unknown_keys_are_ignored(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql://x\nVISION_PORT=8300\n", encoding="utf-8")

    assert Settings(_env_file=env_file).vision_port == 8300


@pytest.mark.parametrize(
    ("model", "family"),
    [
        ("yoloe-11s-seg.pt", ModelFamily.YOLOE),
        ("yoloe-v8m-seg.pt", ModelFamily.YOLOE),
        ("yolov8s-worldv2.pt", ModelFamily.YOLO_WORLD),
    ],
)
def test_family_of(model: str, family: ModelFamily) -> None:
    assert family_of(model) is family


@pytest.mark.parametrize(
    "model", ["yolo11n.pt", "../yoloe-11s-seg.pt", "yoloe-11s-seg", "a/yoloe.pt"]
)
def test_rejects_other_checkpoints(model: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, detector_model=model)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"vision_port": 0},
        {"vision_port": 70000},
        {"detector_device": "tpu"},
        {"detector_conf": 1.5},
        {"detector_max_detections": 0},
        {"detector_max_detections": 301},
        {"vision_max_image_bytes": 0},
    ],
)
def test_rejects_out_of_range_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("device", ["cpu", "mps", "cuda", "cuda:1"])
def test_accepts_devices(device: str) -> None:
    assert Settings(_env_file=None, detector_device=device).detector_device == device


def test_relative_weights_dir_starts_at_the_service_directory() -> None:
    settings = Settings(_env_file=None, vision_weights_dir=Path("models"))

    assert settings.vision_weights_dir == SERVICE_DIR / "models"
