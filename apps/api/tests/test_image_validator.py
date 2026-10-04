from __future__ import annotations

import io
from typing import Any

import pytest
from PIL import ExifTags, Image

from src.pipeline import image_validator
from src.pipeline.image_validator import (
    MODEL_MAX_PIXELS,
    ImageRejectedCode,
    ImageRejectedError,
    model_size,
    validate_image,
)
from src.pipeline.schemas import CaptureLocation, ImageFormat, ImageUpload

LIMITS = {"max_bytes": 10_000_000, "max_pixels": 10_000_000}
RED = (255, 0, 0)
BLUE = (0, 0, 255)


def halves(size: tuple[int, int] = (80, 40), mode: str = "RGB") -> Image.Image:
    """Left half red, right half blue: shows which way an image was turned."""
    image = Image.new("RGB", size, RED)
    image.paste(BLUE, (size[0] // 2, 0, size[0], size[1]))
    return image.convert(mode)


def gps_ifd(**overrides: Any) -> dict[int, Any]:
    gps = {
        ExifTags.GPS.GPSLatitudeRef: "S",
        ExifTags.GPS.GPSLatitude: (36.0, 48.0, 30.0),
        ExifTags.GPS.GPSLongitudeRef: "W",
        ExifTags.GPS.GPSLongitude: (10.0, 10.0, 0.0),
        ExifTags.GPS.GPSAltitudeRef: b"\x01",
        ExifTags.GPS.GPSAltitude: 12.5,
    }
    gps.update({ExifTags.GPS[name]: value for name, value in overrides.items()})
    return {key: value for key, value in gps.items() if value is not None}


def encode(
    image: Image.Image,
    image_format: str = "JPEG",
    *,
    orientation: int | None = None,
    gps: dict[int, Any] | None = None,
    **params: Any,
) -> bytes:
    exif = Image.Exif()
    exif[ExifTags.Base.Make] = "SecretCam"
    if orientation:
        exif[ExifTags.Base.Orientation] = orientation
    if gps is not None:
        exif[ExifTags.IFD.GPSInfo] = gps
    buffer = io.BytesIO()
    image.save(buffer, image_format, exif=exif.tobytes(), **params)
    return buffer.getvalue()


def check(data: bytes, **limits: int):
    return validate_image(ImageUpload(data=data), **{**LIMITS, **limits})


def reopen(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


def assert_no_metadata(data: bytes) -> None:
    image = reopen(data)
    assert image.format == "JPEG"
    assert dict(image.getexif()) == {}
    assert set(image.info) <= {"jfif", "jfif_version", "jfif_unit", "jfif_density"}
    assert b"Exif" not in data
    assert b"SecretCam" not in data
    assert b"ICC_PROFILE" not in data


# ─── Accepted photos ───────────────────────────────────────────────


def test_a_jpeg_is_turned_upright_stripped_and_its_gps_kept_apart():
    data = encode(halves(), orientation=6, gps=gps_ifd(), icc_profile=b"icc" * 50)

    result = check(data)

    assert result.source_format is ImageFormat.JPEG
    assert result.source_bytes == len(data)
    assert result.capture.location == CaptureLocation(
        latitude=-(36 + 48 / 60 + 30 / 3600), longitude=-(10 + 10 / 60), altitude_m=-12.5
    )
    # Orientation 6 turns the image a quarter clockwise: the left half is now on top.
    upright = reopen(result.image.data)
    assert (result.image.width, result.image.height) == upright.size == (40, 80)
    assert upright.getpixel((20, 10))[0] > 200
    assert upright.getpixel((20, 70))[2] > 200
    for encoded in (result.image, result.model_image):
        assert encoded.mime == "image/jpeg"
        assert_no_metadata(encoded.data)


def test_a_photo_without_gps_has_no_location_and_the_altitude_is_optional():
    assert check(encode(halves())).capture.location is None

    data = encode(halves(), gps=gps_ifd(GPSAltitude=None, GPSLatitudeRef=b"N", GPSLongitudeRef="E"))
    location = check(data).capture.location

    assert location is not None
    assert location.latitude > 0
    assert location.longitude > 0
    assert location.altitude_m is None


def test_zero_is_a_coordinate_and_an_altitude_above_sea_is_positive():
    gps = gps_ifd(
        GPSLatitude=(0.0, 0.0, 0.0),
        GPSLongitude=(0.0, 0.0, 0.0),
        GPSAltitudeRef=0,
        GPSAltitude=30.0,
    )

    location = check(encode(halves(), gps=gps)).capture.location

    assert location == CaptureLocation(latitude=0.0, longitude=0.0, altitude_m=30.0)


@pytest.mark.parametrize(
    "gps",
    [
        gps_ifd(GPSLatitude=None),
        gps_ifd(GPSLongitude=None),
        gps_ifd(GPSLatitude=(1.0, 2.0)),
        gps_ifd(GPSLatitude=(95.0, 0.0, 0.0)),
    ],
)
def test_a_missing_or_impossible_position_is_dropped_not_guessed(gps):
    assert check(encode(halves(), gps=gps)).capture.location is None


def test_a_position_that_is_not_a_number_is_dropped():
    assert image_validator._degrees((float("nan"), 0.0, 0.0), "N") is None
    assert image_validator._altitude(float("inf"), 0) is None


def test_a_png_with_transparency_is_flattened_on_white():
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    image.paste((0, 0, 255, 255), (0, 0, 32, 64))

    result = check(encode(image, "PNG"))

    flat = reopen(result.image.data)
    assert result.source_format is ImageFormat.PNG
    assert flat.mode == "RGB"
    assert min(flat.getpixel((50, 10))) > 240
    assert flat.getpixel((10, 10))[2] > 200
    assert_no_metadata(result.image.data)


def test_a_palette_png_with_a_transparent_colour_is_flattened_too():
    image = halves((64, 64)).convert("P")
    image.info["transparency"] = 0

    result = check(encode(image, "PNG", transparency=0))

    assert reopen(result.image.data).mode == "RGB"


@pytest.mark.parametrize("mode", ["L", "CMYK", "LA"])
def test_other_modes_are_converted_to_rgb(mode):
    image_format = "PNG" if mode == "LA" else "JPEG"

    result = check(encode(halves((64, 64), mode), image_format))

    assert reopen(result.model_image.data).mode == "RGB"


def test_a_webp_is_accepted_and_stripped():
    data = encode(halves((96, 64)), "WEBP", gps=gps_ifd())

    result = check(data)

    assert result.source_format is ImageFormat.WEBP
    assert result.capture.location is not None
    assert_no_metadata(result.image.data)


def test_a_large_photo_gets_a_smaller_model_copy_with_32_pixel_sides():
    result = check(encode(halves((2000, 1500))))

    assert (result.image.width, result.image.height) == (2000, 1500)
    width, height = result.model_image.width, result.model_image.height
    assert width % 32 == 0
    assert height % 32 == 0
    assert width * height <= MODEL_MAX_PIXELS
    assert reopen(result.model_image.data).size == (width, height)


def test_a_photo_already_at_the_model_size_is_encoded_once():
    result = check(encode(halves((1344, 768))))

    assert result.model_image is result.image


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ((1344, 768), (1344, 768)),
        ((768, 1344), (768, 1344)),
        ((4000, 3000), (1152, 896)),
        ((3000, 4000), (896, 1152)),
        ((40, 80), (32, 64)),
        ((10_000, 33), (9984, 32)),
        ((33, 10_000), (32, 9984)),
    ],
)
def test_model_size(size, expected):
    assert model_size(*size) == expected


# ─── Refused photos ────────────────────────────────────────────────


def rejected(data: bytes, **limits: int) -> ImageRejectedCode:
    with pytest.raises(ImageRejectedError) as caught:
        check(data, **limits)
    assert caught.value.detail in str(caught.value)
    return caught.value.code


def test_an_empty_upload_is_refused():
    assert rejected(b"") is ImageRejectedCode.EMPTY


def test_too_many_bytes_are_refused_before_decoding():
    assert rejected(b"\xff\xd8\xff" + b"0" * 100, max_bytes=50) is ImageRejectedCode.TOO_LARGE


def test_too_many_pixels_are_refused_from_the_header():
    assert rejected(encode(halves((200, 100))), max_pixels=19_999) is ImageRejectedCode.TOO_LARGE


def test_a_decompression_bomb_is_refused(monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    bomb = encode(halves((100, 20)))
    huge = encode(halves((100, 30)))

    # Pillow warns past its limit and refuses past twice the limit: both are refusals here.
    assert rejected(bomb) is ImageRejectedCode.TOO_LARGE
    assert rejected(huge) is ImageRejectedCode.TOO_LARGE


def test_a_tiny_image_is_refused():
    assert rejected(encode(halves((31, 200)))) is ImageRejectedCode.TOO_SMALL


@pytest.mark.parametrize(
    "data",
    [
        b"GIF89a" + b"\x00" * 50,
        b"RIFF\x00\x00\x00\x00WAVEfmt ",
        b"\x00\x00\x00\x00\x00\x00\x00\x00WEBP",
        b"%PDF-1.7",
    ],
)
def test_other_formats_are_refused(data):
    assert rejected(data) is ImageRejectedCode.UNSUPPORTED


@pytest.mark.parametrize(
    "data",
    [
        b"\xff\xd8\xff\xe0" + b"\x00" * 40,
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 40,
        b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 20,
    ],
)
def test_bytes_that_claim_a_format_but_do_not_decode_are_refused(data):
    assert rejected(data) is ImageRejectedCode.INVALID


def test_a_truncated_jpeg_is_refused():
    data = encode(halves((400, 300)))

    assert rejected(data[: len(data) // 2]) is ImageRejectedCode.INVALID


def test_unreadable_exif_leaves_the_location_empty(monkeypatch):
    def broken(self):
        raise ValueError

    monkeypatch.setattr(Image.Image, "getexif", broken)

    assert image_validator._gps_location(halves()) is None
