"""Shared fixtures: fake Ultralytics models, in-memory images and settings that read nothing."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from vision.config import Settings

EXIF_ORIENTATION = 0x0112
COCO_NAMES = {0: "person", 1: "bicycle", 2: "car"}


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """A developer's environment must never change a test."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


@pytest.fixture
def weights_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "weights"
    directory.mkdir()
    return directory


@pytest.fixture
def settings(weights_dir: Path) -> Settings:
    return Settings(_env_file=None, vision_weights_dir=weights_dir, vision_warmup=False)


def image_bytes(
    size: tuple[int, int] = (40, 20),
    fmt: str = "PNG",
    mode: str = "RGB",
    orientation: int | None = None,
) -> bytes:
    """Encode a plain picture; `orientation` writes the EXIF tag a phone would."""
    image = Image.new(mode, size, "white")
    buffer = BytesIO()
    kwargs: dict[str, Any] = {}
    if orientation is not None:
        exif = Image.Exif()
        exif[EXIF_ORIENTATION] = orientation
        kwargs["exif"] = exif
    image.save(buffer, fmt, **kwargs)
    return buffer.getvalue()


class FakeTensor:
    """What the detector reads from a tensor: `tolist()`."""

    def __init__(self, values: list[Any]) -> None:
        self._values = values

    def tolist(self) -> list[Any]:
        return self._values


class FakeModel:
    """Stands in for an Ultralytics model; it records what it was asked and never loads weights."""

    def __init__(
        self,
        names: dict[int, str] | None = None,
        rows: list[tuple[float, float, float, float, float, int]] | None = None,
        set_classes_error: Exception | None = None,
    ) -> None:
        # A YOLOE checkpoint reports placeholder names until it is given a vocabulary.
        self.names = names if names is not None else {i: str(i) for i in range(80)}
        self.rows = rows or []
        self.set_classes_error = set_classes_error
        self.calls: list[tuple[str, Any]] = []
        self.received_sizes: list[tuple[int, int]] = []

    def get_text_pe(self, labels: list[str]) -> str:
        self.calls.append(("get_text_pe", labels))
        return "embeddings"

    def set_classes(self, labels: list[str], embeddings: Any = None) -> None:
        self.calls.append(("set_classes", (labels, embeddings)))
        if self.set_classes_error is not None:
            raise self.set_classes_error
        self.names = dict(enumerate(labels))

    def predict(self, image: Image.Image, **kwargs: Any) -> list[Any]:
        self.calls.append(("predict", kwargs))
        self.received_sizes.append(image.size)
        boxes = SimpleNamespace(
            xyxy=FakeTensor([list(row[:4]) for row in self.rows]),
            conf=FakeTensor([row[4] for row in self.rows]),
            cls=FakeTensor([float(row[5]) for row in self.rows]),
        )
        return [SimpleNamespace(boxes=boxes, names=self.names)]

    def count(self, name: str) -> int:
        return sum(1 for call, _ in self.calls if call == name)
