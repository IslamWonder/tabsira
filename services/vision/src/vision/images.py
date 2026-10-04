"""Image validation: size limits, format, decompression bombs and EXIF orientation."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from vision.errors import VisionError

# Formats a browser or a phone produces. Pillow only tries these, so a file that
# claims another format is rejected as such, not decoded by a rarely used plugin.
ALLOWED_FORMATS = ("JPEG", "PNG", "WEBP")

# Importing Ultralytics replaces `PIL.Image.open` with a version that, when a file does
# not open, tries to install a HEIF plugin. Keep Pillow's own: this module is imported
# before Ultralytics is, so what is captured here is the original.
PILLOW_OPEN = Image.open


def _refuse_too_many_pixels(image: Image.Image, max_pixels: int) -> None:
    """Raise Pillow's own bomb error, so one handler covers its guard and ours."""
    if image.width * image.height > max_pixels:
        message = f"{image.width}x{image.height} exceeds {max_pixels} pixels"
        raise Image.DecompressionBombError(message)


def decode_image(data: bytes, *, max_bytes: int, max_pixels: int) -> Image.Image:
    """
    Return the image as RGB, upright according to its EXIF orientation.

    The header is read first, so an image that would decode to too many pixels is
    refused before its pixels are allocated. `verify()` then checks the file's
    structure, and a second open decodes it.
    """
    if not data:
        raise VisionError(400, "empty_image", "No image bytes were received.")
    if len(data) > max_bytes:
        raise VisionError(413, "image_too_large", f"The image is larger than {max_bytes} bytes.")

    try:
        probe = PILLOW_OPEN(BytesIO(data), formats=ALLOWED_FORMATS)
        _refuse_too_many_pixels(probe, max_pixels)
        probe.verify()
        image = PILLOW_OPEN(BytesIO(data), formats=ALLOWED_FORMATS)
        image.load()
    except Image.DecompressionBombError as exc:
        raise VisionError(413, "image_too_large", "The image has too many pixels.") from exc
    except UnidentifiedImageError as exc:
        raise VisionError(
            415, "unsupported_media_type", "The file is not a JPEG, PNG or WebP image."
        ) from exc
    except Exception as exc:  # Pillow raises assorted types for corrupt or truncated files
        raise VisionError(400, "invalid_image", "The image could not be decoded.") from exc

    # Phone photos carry an orientation tag; boxes must match the picture people see.
    return ImageOps.exif_transpose(image).convert("RGB")
