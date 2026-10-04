"""
Photos in, clean JPEGs out (decision 8 and `docs/spec/master-prompt-v2.md` section 19).

`process_photo` does two things, in this order, to the file exactly as the person sent it:

1. **It reads what the camera recorded about where and when** (`CaptureMetadata`): the GPS
   position, its accuracy and time, and the moment the photo was taken. This is the original
   file's EXIF, read before anything is changed, because re-encoding removes it. It is private
   capture metadata with the source `photo_exif`: the caller decides what to do with it (the
   atlas asks the owner to confirm a place), and it is never part of the stored image.
2. **It re-encodes the pixels as a new JPEG with no metadata at all**: no EXIF, no GPS, no
   XMP, no IPTC, no maker notes, no comments, no thumbnail, no serial numbers, and no ICC
   profile. A profile is "kept only if needed for colour" by being applied instead: the pixels
   are converted to sRGB, which is what every browser assumes when a file has no profile, and
   the profile is then no longer needed. The image is turned upright first (the orientation
   tag is metadata and goes), flattened on white when it has transparency, and shrunk to at most
   `MAX_SIDE` pixels on its longer side.

What this module does not do: decide whether a photo may be kept (that is
`src/storage/photos.py`), or store anything. A guest's photo is processed too, for its capture
metadata and for the analysis, and then dropped.

The work is CPU-bound and synchronous; call `process_photo_in_thread` from a route.

Capture metadata is private. Its position and accuracy are left out of its `repr`, so a log
line that prints the object cannot leak them, and nothing here logs a value from a file.
"""

from __future__ import annotations

import asyncio
import io
import logging
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from PIL import ExifTags, Image, ImageCms, ImageOps, UnidentifiedImageError

from src import clock

log = logging.getLogger("tabsira.images")

# What the capture metadata says it came from (extension-atlas-camera.md, section 3).
PHOTO_EXIF = "photo_exif"

# The formats a person may send. HEIC is not among them: Pillow cannot read it without a plugin.
ACCEPTED_FORMATS = frozenset({"JPEG", "MPO", "PNG", "WEBP"})
MAX_INPUT_BYTES = 25 * 1024 * 1024
# A phone sensor is 12 to 50 megapixels. Above this the file is refused before it is decoded.
MAX_PIXELS = 50_000_000
# The longer side of what is kept. A phone screen shows well under this.
MAX_SIDE = 2560
JPEG_QUALITY = 85
JPEG_CONTENT_TYPE = "image/jpeg"

# Why a file is refused: the `reason` of an `ImageRejectedError`.
TOO_LARGE = "too_large"
TOO_MANY_PIXELS = "too_many_pixels"
UNSUPPORTED = "unsupported"
UNREADABLE = "unreadable"

# A clock set wrong writes dates that are not real. Before this year, or more than two days
# ahead of now (a time zone is at most 14 hours), a capture time is not believed.
_EARLIEST_YEAR = 1990
_FUTURE_MARGIN = timedelta(days=2)

# EXIF tag numbers that Pillow's enums name only some of.
_DATETIME_ORIGINAL = 0x9003
_DATETIME_DIGITIZED = 0x9004
_OFFSET_TIME_ORIGINAL = 0x9011
_OFFSET_TIME_DIGITIZED = 0x9012
_GPS_H_POSITIONING_ERROR = 0x1F
_OFFSET = re.compile(r"^([+-])(\d{2}):(\d{2})$")


class ImageRejectedError(Exception):
    """The file is not a photo this service will take; `reason` says why, in a word."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class CaptureMetadata:
    """
    What the camera recorded, from the original file's EXIF. Private to the photo's owner.

    `latitude` and `longitude` are in degrees (WGS84), south and west negative, and are both set
    or both None; a coordinate of zero is a value, not a missing one. `accuracy_meters` is the
    camera's own horizontal error, when it wrote one. `captured_at` is when the photo was taken,
    timezone-aware when the file gives its UTC offset and otherwise the camera's wall clock,
    without a zone: never the upload time, and None when the file has no date.
    `location_measured_at` is when the GPS fix was taken, in UTC. EXIF can be wrong or edited:
    none of this proves that anyone was anywhere.
    """

    latitude: float | None = field(default=None, repr=False)
    longitude: float | None = field(default=None, repr=False)
    accuracy_meters: float | None = field(default=None, repr=False)
    captured_at: datetime | None = field(default=None, repr=False)
    location_measured_at: datetime | None = field(default=None, repr=False)
    source: str = PHOTO_EXIF

    @property
    def has_location(self) -> bool:
        """Whether the file carried a usable position."""
        return self.latitude is not None and self.longitude is not None


@dataclass(frozen=True)
class ProcessedPhoto:
    """A photo ready to analyse or to keep: clean JPEG bytes, and what was read before cleaning."""

    data: bytes = field(repr=False)
    width: int
    height: int
    capture: CaptureMetadata | None = field(repr=False)
    content_type: str = JPEG_CONTENT_TYPE


# ─── Reading the camera's record ──────────────────────────────────────────────


def _number(value: Any) -> float | None:
    """Return `value` as a finite float, or None. Rationals with a zero denominator are NaN."""
    try:
        number = float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return number if math.isfinite(number) else None


def _coordinate(value: Any, ref: Any, positive: str, negative: str, limit: float) -> float | None:
    """Turn EXIF degrees, minutes and seconds and a hemisphere letter into signed degrees."""
    if not isinstance(value, Sequence) or isinstance(value, str | bytes) or len(value) != 3:
        return None
    parts = [_number(part) for part in value]
    if not isinstance(ref, str) or None in parts:
        return None
    degrees, minutes, seconds = (part for part in parts if part is not None)
    if not (0 <= degrees <= limit and 0 <= minutes < 60 and 0 <= seconds < 60):
        return None
    hemisphere = ref.strip().upper()
    if hemisphere not in {positive, negative}:
        return None
    result = degrees + minutes / 60 + seconds / 3600
    if result > limit:
        return None
    return result if hemisphere == positive else -result


def _position(gps: dict[int, Any]) -> tuple[float, float] | None:
    latitude = _coordinate(
        gps.get(ExifTags.GPS.GPSLatitude), gps.get(ExifTags.GPS.GPSLatitudeRef), "N", "S", 90.0
    )
    longitude = _coordinate(
        gps.get(ExifTags.GPS.GPSLongitude), gps.get(ExifTags.GPS.GPSLongitudeRef), "E", "W", 180.0
    )
    if latitude is None or longitude is None:
        return None
    # Exactly 0, 0 is what a camera with no fix writes: a point in the sea off West Africa
    # that nobody photographs. One coordinate being zero is fine (the equator, Greenwich).
    if latitude == 0 and longitude == 0:
        return None
    return latitude, longitude


def _zone(offset: Any) -> timezone | None:
    """Return the UTC offset an EXIF `+01:00` names, or None when there is none or it is odd."""
    if not isinstance(offset, str):
        return None
    match = _OFFSET.match(offset.strip())
    if match is None:
        return None
    hours, minutes = int(match[2]), int(match[3])
    if hours > 14 or minutes > 59:
        return None
    delta = timedelta(hours=hours, minutes=minutes)
    return timezone(delta if match[1] == "+" else -delta)


def _believable(moment: datetime) -> bool:
    if moment.year < _EARLIEST_YEAR:
        return False
    now = clock.utcnow()
    comparable = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    return comparable <= now + _FUTURE_MARGIN


def _taken(details: dict[int, Any]) -> datetime | None:
    """
    Return when the photo was taken, from the original or the digitised time, never the edit time.

    The EXIF `DateTime` tag is when the file was last saved, which is not when the photo was
    taken; it is not read.
    """
    for tag, offset_tag in (
        (_DATETIME_ORIGINAL, _OFFSET_TIME_ORIGINAL),
        (_DATETIME_DIGITIZED, _OFFSET_TIME_DIGITIZED),
    ):
        text = details.get(tag)
        if not isinstance(text, str):
            continue
        try:
            moment = datetime.strptime(text.strip().rstrip("\x00"), "%Y:%m:%d %H:%M:%S")
        except ValueError:
            continue
        zone = _zone(details.get(offset_tag))
        if zone is not None:
            moment = moment.replace(tzinfo=zone)
        if _believable(moment):
            return moment
    return None


def _fix_time(gps: dict[int, Any]) -> datetime | None:
    """Return when the GPS fix was taken, in UTC, from its date and time stamps."""
    stamp, clock_parts = gps.get(ExifTags.GPS.GPSDateStamp), gps.get(ExifTags.GPS.GPSTimeStamp)
    if not isinstance(stamp, str) or not isinstance(clock_parts, Sequence):
        return None
    numbers = [_number(part) for part in clock_parts]
    if len(numbers) != 3 or None in numbers:
        return None
    hour, minute, second = (int(n) for n in numbers if n is not None)
    try:
        day = datetime.strptime(stamp.strip().rstrip("\x00"), "%Y:%m:%d")
        moment = day.replace(hour=hour, minute=minute, second=second, tzinfo=UTC)
    except ValueError:
        return None
    return moment if _believable(moment) else None


def read_capture_metadata(image: Image.Image) -> CaptureMetadata | None:
    """
    Read the camera's record of where and when from an opened, not yet changed, image.

    Returns None when there is nothing usable. A file whose EXIF cannot be parsed has none: the
    photo is still processed, and nothing about the failure is logged beyond its type.
    """
    try:
        exif = image.getexif()
        gps = dict(exif.get_ifd(ExifTags.IFD.GPSInfo))
        details = dict(exif.get_ifd(ExifTags.IFD.Exif))
    except Exception as error:
        log.warning("The photo's EXIF could not be read: %s.", type(error).__name__)
        return None
    position = _position(gps)
    accuracy = _number(gps.get(_GPS_H_POSITIONING_ERROR))
    metadata = CaptureMetadata(
        latitude=position[0] if position else None,
        longitude=position[1] if position else None,
        accuracy_meters=accuracy if position and accuracy is not None and accuracy >= 0 else None,
        captured_at=_taken(details),
        location_measured_at=_fix_time(gps) if position else None,
    )
    if not (metadata.has_location or metadata.captured_at):
        return None
    return metadata


# ─── Writing a clean image ────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _srgb() -> ImageCms.ImageCmsProfile:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))


def _flatten(image: Image.Image) -> Image.Image:
    """Put an image with transparency on white; return any other unchanged."""
    if image.mode == "P":
        image = image.convert("RGBA")
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        page = Image.new("RGB", rgba.size, (255, 255, 255))
        page.paste(rgba, mask=rgba.getchannel("A"))
        return page
    return image


def _to_srgb(image: Image.Image, profile: bytes | None) -> Image.Image:
    """Apply the file's own colour profile and return plain RGB, or take the pixels as they are."""
    if profile is not None:
        try:
            converted = ImageCms.profileToProfile(
                image, ImageCms.ImageCmsProfile(io.BytesIO(profile)), _srgb(), outputMode="RGB"
            )
        except (ImageCms.PyCMSError, OSError, ValueError) as error:
            log.warning("A colour profile could not be applied: %s.", type(error).__name__)
        else:
            if converted is not None:
                return converted
    return image.convert("RGB")


def _clean_jpeg(image: Image.Image, profile: bytes | None) -> tuple[bytes, int, int]:
    upright = ImageOps.exif_transpose(image)
    rgb = _to_srgb(_flatten(upright), profile)
    rgb.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    # A new image from the pixels alone: nothing the old one carried can come along.
    clean = Image.new("RGB", rgb.size)
    clean.paste(rgb)
    out = io.BytesIO()
    clean.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return out.getvalue(), clean.width, clean.height


def _open(raw: bytes) -> Image.Image:
    if len(raw) > MAX_INPUT_BYTES:
        raise ImageRejectedError(TOO_LARGE)
    try:
        image = Image.open(io.BytesIO(raw))
    except Image.DecompressionBombError:
        raise ImageRejectedError(TOO_MANY_PIXELS) from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise ImageRejectedError(UNREADABLE) from None
    if image.format not in ACCEPTED_FORMATS:
        raise ImageRejectedError(UNSUPPORTED)
    if image.width * image.height > MAX_PIXELS:
        raise ImageRejectedError(TOO_MANY_PIXELS)
    return image


def process_photo(raw: bytes) -> ProcessedPhoto:
    """
    Read the capture metadata of `raw`, then return it as a clean JPEG with the metadata aside.

    Raises `ImageRejectedError` with the reason `too_large`, `too_many_pixels`, `unsupported` or
    `unreadable`. Nothing is written anywhere.
    """
    image = _open(raw)
    capture = read_capture_metadata(image)
    profile = image.info.get("icc_profile")
    try:
        image.load()
        data, width, height = _clean_jpeg(image, profile if isinstance(profile, bytes) else None)
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise ImageRejectedError(UNREADABLE) from None
    return ProcessedPhoto(data=data, width=width, height=height, capture=capture)


async def process_photo_in_thread(raw: bytes) -> ProcessedPhoto:
    """Run `process_photo` off the event loop: decoding a large photo takes a good fraction of a second."""
    return await asyncio.to_thread(process_photo, raw)
