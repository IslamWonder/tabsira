from __future__ import annotations

import pytest
from PIL import Image

from tests.conftest import image_bytes
from vision.errors import VisionError
from vision.images import PILLOW_OPEN, decode_image

LIMITS = {"max_bytes": 1_000_000, "max_pixels": 10_000}


def decode(data: bytes, **overrides: int) -> Image.Image:
    return decode_image(data, **{**LIMITS, **overrides})


def failure(data: bytes, **overrides: int) -> VisionError:
    with pytest.raises(VisionError) as caught:
        decode(data, **overrides)
    return caught.value


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_decodes_the_accepted_formats(fmt: str) -> None:
    image = decode(image_bytes((40, 20), fmt))

    assert image.size == (40, 20)
    assert image.mode == "RGB"


@pytest.mark.parametrize("mode", ["RGBA", "L", "P"])
def test_converts_other_modes_to_rgb(mode: str) -> None:
    assert decode(image_bytes((8, 8), "PNG", mode)).mode == "RGB"


def test_applies_the_exif_orientation_before_detection() -> None:
    # Orientation 6: the sensor image is stored lying down and shown rotated by 90 degrees.
    assert decode(image_bytes((40, 20), "JPEG", orientation=6)).size == (20, 40)


def test_keeps_an_upright_image_upright() -> None:
    assert decode(image_bytes((40, 20), "JPEG", orientation=1)).size == (40, 20)


def test_pillows_own_open_is_used_even_after_ultralytics_replaces_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def ultralytics_open(*_args: object, **_kwargs: object) -> Image.Image:
        message = "pi_heif is not installed"
        raise ImportError(message)

    monkeypatch.setattr(Image, "open", ultralytics_open)

    assert PILLOW_OPEN.__module__ == "PIL.Image"
    assert failure(b"not an image").status == 415
    assert decode(image_bytes()).size == (40, 20)


def test_refuses_no_bytes() -> None:
    error = failure(b"")

    assert (error.status, error.code) == (400, "empty_image")


def test_refuses_too_many_bytes() -> None:
    error = failure(image_bytes(), max_bytes=10)

    assert (error.status, error.code) == (413, "image_too_large")


def test_refuses_too_many_pixels_before_decoding_them() -> None:
    error = failure(image_bytes((200, 100)), max_pixels=10_000)

    assert (error.status, error.code) == (413, "image_too_large")


def test_accepts_exactly_the_pixel_limit() -> None:
    assert decode(image_bytes((100, 100)), max_pixels=10_000).size == (100, 100)


def test_pillow_decompression_bomb_guard_is_a_413_too(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)

    error = failure(image_bytes((20, 20)))

    assert (error.status, error.code) == (413, "image_too_large")


@pytest.mark.parametrize(
    "data", [b"not an image at all", b"%PDF-1.7 ...", b"GIF89a" + b"\x00" * 20]
)
def test_refuses_what_is_not_an_accepted_image(data: bytes) -> None:
    error = failure(data)

    assert (error.status, error.code) == (415, "unsupported_media_type")


@pytest.mark.parametrize("fmt", ["GIF", "BMP"])
def test_refuses_real_images_of_other_formats(fmt: str) -> None:
    error = failure(image_bytes((8, 8), fmt))

    assert error.status == 415


def test_refuses_a_truncated_image() -> None:
    data = image_bytes((200, 100), "JPEG")

    error = failure(data[: len(data) // 2])

    assert (error.status, error.code) == (400, "invalid_image")


def test_refuses_a_corrupt_png() -> None:
    data = bytearray(image_bytes((20, 20), "PNG"))
    start = data.index(b"IDAT") + 6
    data[start : start + 4] = b"\xff\xff\xff\xff"  # pixel data, so the chunk checksum fails

    assert failure(bytes(data)).code == "invalid_image"
