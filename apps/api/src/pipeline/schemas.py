"""
The schemas the scan pipeline's stages take and return.

Each stage is a function from one of these models to another (v2 §6). Boxes
are always ratios (0 to 1) of the image, `x` and `y` being the top-left corner;
pixel and 0-1000 boxes exist only inside the stage that converts them.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Ratio = Annotated[float, Field(ge=0, le=1)]


class FrozenModel(BaseModel):
    """A stage value: immutable, and bytes travel as base64 if it is ever serialised."""

    model_config = ConfigDict(frozen=True, ser_json_bytes="base64", val_json_bytes="base64")


# ─── Image ─────────────────────────────────────────────────────────


class ImageFormat(StrEnum):
    """The formats a photo may arrive in."""

    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"


class ImageUpload(FrozenModel):
    """The bytes of a photo as received, before any check."""

    data: bytes


class EncodedImage(FrozenModel):
    """A JPEG with every metadata block removed: what may leave the server."""

    data: bytes
    mime: str = "image/jpeg"
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]


class CaptureLocation(FrozenModel):
    """Where the camera says the photo was taken. Zero is a value, not a missing one."""

    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]
    altitude_m: float | None = None


class CaptureMetadata(FrozenModel):
    """
    Private facts about the capture, kept apart from the image.

    It never reaches a model and never a public API; the atlas may offer it to
    the owner as a starting point, and approximates it on the server.
    """

    location: CaptureLocation | None = None


class ValidatedImage(FrozenModel):
    """A photo that passed the checks, upright, re-encoded without metadata."""

    source_format: ImageFormat
    source_bytes: int
    # Full size, for the owner's consented storage.
    image: EncodedImage
    # The copy every model and the detector receive (see image_validator.model_size).
    model_image: EncodedImage
    capture: CaptureMetadata
