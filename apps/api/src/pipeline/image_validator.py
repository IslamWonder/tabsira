"""
ImageValidator: the first stage of a scan.

A photo is accepted only as JPEG, PNG or WebP, within a byte and a pixel limit
(the pixel count is read from the header, before anything is decoded). It is
turned upright from its EXIF orientation, flattened to RGB and re-encoded as a
JPEG that carries no metadata at all: no EXIF, no GPS, no ICC profile, no XMP.
The GPS position, if the camera wrote one, is read before stripping and
returned on its own, as private capture metadata; it never travels with the
image bytes that go to a model or to the detector.
"""

from __future__ import annotations

import io
import math
import warnings
from enum import StrEnum
from typing import Any

from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError

from src.pipeline.schemas import (
    CaptureLocation,
    CaptureMetadata,
    EncodedImage,
    ImageFormat,
    ImageUpload,
    ValidatedImage,
)

# Smaller than this, nothing in the photo can be recognised.
MIN_SIDE = 32
# Vision models tile an image in 32-pixel blocks (Qwen-VL: 16-pixel patches,
# merged two by two). A copy with both sides a multiple of 32 and about one
# megapixel is seen as it is, with no hidden resize, so the boxes a model
# returns refer to exactly the pixels we sent.
MODEL_BLOCK = 32
MODEL_MAX_PIXELS = 1024 * 1024
JPEG_QUALITY = 90

_SIGNATURES: tuple[tuple[ImageFormat, bytes, int], ...] = (
    (ImageFormat.JPEG, b"\xff\xd8\xff", 0),
    (ImageFormat.PNG, b"\x89PNG\r\n\x1a\n", 0),
    (ImageFormat.WEBP, b"WEBP", 8),
)
_PILLOW_FORMATS = {ImageFormat.JPEG: "JPEG", ImageFormat.PNG: "PNG", ImageFormat.WEBP: "WEBP"}


class ImageRejectedCode(StrEnum):
    """Why a photo was refused. Stable: the client maps each to an Arabic message."""

    EMPTY = "empty_image"
    TOO_LARGE = "image_too_large"
    TOO_SMALL = "image_too_small"
    UNSUPPORTED = "unsupported_media_type"
    INVALID = "invalid_image"


class ImageRejectedError(Exception):
    """The photo cannot be used; `code` says why."""

    def __init__(self, code: ImageRejectedCode, detail: str) -> None:
        super().__init__(f"{code.value}: {detail}")
        self.code = code
        self.detail = detail


def validate_image(upload: ImageUpload, *, max_bytes: int, max_pixels: int) -> ValidatedImage:
    """Check a photo and return it upright and stripped, with its GPS kept apart."""
    data = upload.data
    if not data:
        raise ImageRejectedError(ImageRejectedCode.EMPTY, "no image bytes")
    if len(data) > max_bytes:
        raise ImageRejectedError(
            ImageRejectedCode.TOO_LARGE, f"{len(data)} bytes, more than {max_bytes}"
        )
    source_format = _sniff(data)
    image = _open(data, source_format, max_pixels)
    location = _gps_location(image)
    upright = _flatten(ImageOps.exif_transpose(image))

    full = _encode(upright)
    size = model_size(upright.width, upright.height)
    model_copy = (
        full if size == upright.size else _encode(upright.resize(size, Image.Resampling.LANCZOS))
    )
    return ValidatedImage(
        source_format=source_format,
        source_bytes=len(data),
        image=full,
        model_image=model_copy,
        capture=CaptureMetadata(location=location),
    )


def model_size(width: int, height: int) -> tuple[int, int]:
    """Return the size of the model copy: at most MODEL_MAX_PIXELS, sides multiples of 32."""
    scale = min(1.0, math.sqrt(MODEL_MAX_PIXELS / (width * height)))
    new_width = max(MODEL_BLOCK, round(width * scale / MODEL_BLOCK) * MODEL_BLOCK)
    new_height = max(MODEL_BLOCK, round(height * scale / MODEL_BLOCK) * MODEL_BLOCK)
    while new_width * new_height > MODEL_MAX_PIXELS:
        if new_width >= new_height:
            new_width -= MODEL_BLOCK
        else:
            new_height -= MODEL_BLOCK
    return new_width, new_height


def _sniff(data: bytes) -> ImageFormat:
    for image_format, signature, offset in _SIGNATURES:
        if data[offset : offset + len(signature)] == signature:
            if image_format is ImageFormat.WEBP and not data.startswith(b"RIFF"):
                continue
            return image_format
    raise ImageRejectedError(ImageRejectedCode.UNSUPPORTED, "not a JPEG, PNG or WebP image")


def _open(data: bytes, image_format: ImageFormat, max_pixels: int) -> Image.Image:
    try:
        with warnings.catch_warnings():
            # Pillow only warns about a very large image; here it is a refusal.
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data), formats=[_PILLOW_FORMATS[image_format]])
            width, height = image.size
            if width * height > max_pixels:
                message = f"{width}x{height} pixels, more than {max_pixels}"
                raise ImageRejectedError(ImageRejectedCode.TOO_LARGE, message)
            if min(width, height) < MIN_SIDE:
                message = f"{width}x{height} pixels, a side under {MIN_SIDE}"
                raise ImageRejectedError(ImageRejectedCode.TOO_SMALL, message)
            image.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ImageRejectedError(ImageRejectedCode.TOO_LARGE, "decompression bomb") from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        message = f"the {image_format.value} data does not decode"
        raise ImageRejectedError(ImageRejectedCode.INVALID, message) from None
    return image


def _flatten(image: Image.Image) -> Image.Image:
    """Return an RGB copy; transparent areas become white, not black."""
    has_alpha = image.mode in {"RGBA", "LA", "PA"} or (
        image.mode == "P" and "transparency" in image.info
    )
    if has_alpha:
        rgba = image.convert("RGBA")
        flat = Image.new("RGB", rgba.size, "white")
        flat.paste(rgba, mask=rgba.getchannel("A"))
        return flat
    return image.convert("RGB")


def _encode(image: Image.Image) -> EncodedImage:
    # A fresh image owns no metadata, so nothing can be carried into the file.
    clean = Image.new("RGB", image.size)
    clean.paste(image)
    buffer = io.BytesIO()
    clean.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return EncodedImage(data=buffer.getvalue(), width=clean.width, height=clean.height)


def _gps_location(image: Image.Image) -> CaptureLocation | None:
    """Read the EXIF GPS position, or None when it is absent or malformed."""
    try:
        gps = image.getexif().get_ifd(ExifTags.IFD.GPSInfo)
        latitude = _degrees(gps.get(ExifTags.GPS.GPSLatitude), gps.get(ExifTags.GPS.GPSLatitudeRef))
        longitude = _degrees(
            gps.get(ExifTags.GPS.GPSLongitude), gps.get(ExifTags.GPS.GPSLongitudeRef)
        )
        if latitude is None or longitude is None:
            return None
        return CaptureLocation(
            latitude=latitude,
            longitude=longitude,
            altitude_m=_altitude(
                gps.get(ExifTags.GPS.GPSAltitude), gps.get(ExifTags.GPS.GPSAltitudeRef)
            ),
        )
    except (TypeError, ValueError, ZeroDivisionError, OSError, KeyError):
        return None


def _degrees(value: Any, reference: Any) -> float | None:
    """Turn EXIF degrees, minutes and seconds into signed decimal degrees."""
    if not isinstance(value, tuple) or len(value) != 3:
        return None
    degrees, minutes, seconds = (float(part) for part in value)
    decimal = degrees + minutes / 60 + seconds / 3600
    if not math.isfinite(decimal):
        return None
    # Pillow reads the ASCII reference tags as text.
    sign = -1.0 if str(reference).strip().upper() in {"S", "W"} else 1.0
    return sign * decimal


def _altitude(value: Any, reference: Any) -> float | None:
    if value is None:
        return None
    altitude = float(value)
    if not math.isfinite(altitude):
        return None
    below_sea = reference in {1, b"\x01"}
    return -altitude if below_sea else altitude
