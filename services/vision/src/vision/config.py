"""
Typed settings of the vision service.

Every key is read from the process environment and from the root `.env`, and is
validated when `Settings` is built. A key added here is added to `.env.example`
in the same commit.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = SERVICE_DIR.parents[1]

# Hard limits that are not worth a setting.
MAX_DETECTIONS_LIMIT = 300
MAX_VOCABULARY = 500

DEFAULT_MODEL = "yoloe-11s-seg.pt"
ALTERNATIVE_MODEL = "yolov8s-worldv2.pt"


class ModelFamily(StrEnum):
    """The two Ultralytics open-vocabulary detectors this service can run."""

    YOLOE = "yoloe"
    YOLO_WORLD = "yolo-world"


def family_of(model: str) -> ModelFamily:
    """Return the family a checkpoint file name belongs to, or raise ValueError."""
    if model.startswith("yoloe"):
        return ModelFamily.YOLOE
    if "world" in model:
        return ModelFamily.YOLO_WORLD
    message = f"{model} is not a YOLOE or YOLO-World checkpoint"
    raise ValueError(message)


class Settings(BaseSettings):
    """Configuration of the vision service."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Address the service binds to. Always loopback; the API is its only caller.
    vision_host: str = "127.0.0.1"
    vision_port: Annotated[int, Field(ge=1, le=65535)] = 8100
    # Where checkpoints and text encoders live. Relative paths start at services/vision.
    vision_weights_dir: Path = SERVICE_DIR / "weights"
    # Upload limits: encoded size, and decoded size (a small file can expand a lot).
    vision_max_image_bytes: Annotated[int, Field(gt=0)] = 15 * 1024 * 1024
    vision_max_image_pixels: Annotated[int, Field(gt=0)] = 40_000_000
    # Load the model at startup instead of on the first request.
    vision_warmup: bool = True

    # YOLOE (default) or YOLO-World checkpoint, by file name.
    detector_model: str = DEFAULT_MODEL
    detector_device: Annotated[str, Field(pattern=r"^(cpu|mps|cuda(:\d+)?)$")] = "cpu"
    # Used when a request does not say.
    detector_conf: Annotated[float, Field(ge=0, le=1)] = 0.2
    detector_max_detections: Annotated[int, Field(ge=1, le=MAX_DETECTIONS_LIMIT)] = 20

    @field_validator("detector_model")
    @classmethod
    def _known_checkpoint(cls, value: str) -> str:
        if Path(value).name != value or not value.endswith(".pt"):
            message = "must be a checkpoint file name ending in .pt, without a path"
            raise ValueError(message)
        family_of(value)
        return value

    @field_validator("vision_weights_dir")
    @classmethod
    def _absolute_weights_dir(cls, value: Path) -> Path:
        return value if value.is_absolute() else SERVICE_DIR / value
