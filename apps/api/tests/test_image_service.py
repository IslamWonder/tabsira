"""
The image service, on real files: the camera's record is read first, then every trace of it goes.

Each photo here is a genuine JPEG, PNG or WebP whose EXIF block was written by `support_images`
in the byte layout a camera uses, little- and big-endian, so what the service reads is not what
the same library wrote.
"""

from __future__ import annotations

import io
import logging
from datetime import UTC, datetime, timedelta, timezone

import pytest
from PIL import ExifTags, Image, ImageCms

from src.services import image_service
from src.services.image_service import (
    PHOTO_EXIF,
    CaptureMetadata,
    ImageRejectedError,
    process_photo,
    process_photo_in_thread,
    read_capture_metadata,
)
from tests.support_images import (
    ASCII,
    RATIONAL,
    SECRET_COMMENT,
    SECRET_MAKER_NOTE,
    SECRET_SERIAL,
    SECRET_XMP,
    dms,
    exif_block,
    jpeg_of,
    marker_codes,
    pixels,
    with_everything,
    with_exif,
    with_segment,
)

TUNIS = (dms(36.8065), "N"), (dms(10.1815), "E")
SYDNEY = (dms(33.8688), "S"), (dms(151.2093), "E")
LIMA = (dms(12.0464), "S"), (dms(77.0428), "W")


def photo(**exif: object) -> bytes:
    """A JPEG that carries the given EXIF fields and everything else a phone embeds."""
    return with_everything(with_exif(jpeg_of(pixels()), exif_block(**exif)))  # type: ignore[arg-type]


def capture_of(data: bytes) -> CaptureMetadata | None:
    return read_capture_metadata(Image.open(io.BytesIO(data)))


def assert_no_metadata(data: bytes) -> None:
    """The bytes carry no EXIF, XMP, IPTC, ICC profile, comment or maker note, and no GPS."""
    assert marker_codes(data)[0] == 0xE0  # the JFIF header, which holds only a pixel density
    assert set(marker_codes(data)) <= {0xE0, 0xDB, 0xC0, 0xC2, 0xC4, 0xDA}
    for secret in (b"Exif", b"http://ns.adobe.com", b"Photoshop", b"ICC_PROFILE", b"IPTC"):
        assert secret not in data
    for secret in (SECRET_MAKER_NOTE, SECRET_COMMENT, SECRET_XMP, SECRET_SERIAL.encode()):
        assert secret not in data
    assert b"TestCamera" not in data
    image = Image.open(io.BytesIO(data))
    assert not image.getexif()
    assert not image.getexif().get_ifd(ExifTags.IFD.GPSInfo)
    assert set(image.info) <= {
        "jfif",
        "jfif_version",
        "jfif_unit",
        "jfif_density",
        "dpi",
        "progressive",
        "progression",
    }
    assert "icc_profile" not in image.info


# ─── The camera's record, read from the original ──────────────────────────────


@pytest.mark.parametrize("big_endian", [False, True])
def test_the_position_is_read_in_either_byte_order(big_endian):
    latitude, longitude = TUNIS

    capture = process_photo(
        photo(big_endian=big_endian, latitude=latitude, longitude=longitude)
    ).capture

    assert capture is not None
    assert capture.has_location
    assert capture.latitude == pytest.approx(36.8065, abs=1e-3)
    assert capture.longitude == pytest.approx(10.1815, abs=1e-3)
    assert capture.source == PHOTO_EXIF == "photo_exif"


@pytest.mark.parametrize(
    ("latitude", "longitude", "expected"),
    [
        (*TUNIS, (36.8065, 10.1815)),
        (*SYDNEY, (-33.8688, 151.2093)),
        (*LIMA, (-12.0464, -77.0428)),
        ((dms(48.8566), "N"), (dms(2.3522), "W"), (48.8566, -2.3522)),
    ],
)
def test_south_and_west_are_negative_and_north_and_east_positive(latitude, longitude, expected):
    capture = capture_of(photo(latitude=latitude, longitude=longitude))

    assert capture is not None
    assert (capture.latitude, capture.longitude) == pytest.approx(expected, abs=1e-3)


def test_a_zero_coordinate_is_a_value_not_a_missing_one():
    on_the_equator = capture_of(photo(latitude=(dms(0.0), "N"), longitude=(dms(32.58), "E")))
    on_greenwich = capture_of(photo(latitude=(dms(51.4779), "N"), longitude=(dms(0.0), "W")))

    assert on_the_equator is not None
    assert (on_the_equator.latitude, on_the_equator.longitude) == (
        0.0,
        pytest.approx(32.58, abs=1e-3),
    )
    assert on_the_equator.has_location
    assert on_greenwich is not None
    assert on_greenwich.longitude == 0.0
    assert on_greenwich.has_location


def test_the_point_a_camera_without_a_fix_writes_is_no_position():
    assert capture_of(photo(latitude=(dms(0.0), "N"), longitude=(dms(0.0), "E"))) is None


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        # A letter that is not a hemisphere of this axis, or no letter.
        ((dms(36.8), "E"), (dms(10.1), "E")),
        ((dms(36.8), "N"), (dms(10.1), "N")),
        ((dms(36.8), ""), (dms(10.1), "E")),
        ((dms(36.8), "n"), (dms(10.1), "x")),
        # Out of range.
        ((dms(91.0), "N"), (dms(10.1), "E")),
        ((dms(36.8), "N"), (dms(181.0), "E")),
        # Minutes or seconds of 60 and over.
        (([(36, 1), (60, 1), (0, 1)], "N"), (dms(10.1), "E")),
        (([(36, 1), (10, 1), (60, 1)], "N"), (dms(10.1), "E")),
        # Degrees, minutes and seconds that add up past the pole.
        (([(90, 1), (30, 1), (0, 1)], "N"), (dms(10.1), "E")),
        # A zero denominator makes the number meaningless.
        (([(36, 0), (0, 1), (0, 1)], "N"), (dms(10.1), "E")),
    ],
)
def test_a_position_that_cannot_be_right_is_ignored_whole(latitude, longitude):
    assert capture_of(photo(latitude=latitude, longitude=longitude)) is None


def test_one_valid_coordinate_without_the_other_is_no_position():
    capture = capture_of(photo(latitude=TUNIS[0], taken="2026:09:30 14:05:09"))

    assert capture is not None
    assert not capture.has_location
    assert (capture.latitude, capture.longitude) == (None, None)
    assert capture.captured_at == datetime(2026, 9, 30, 14, 5, 9)


@pytest.mark.parametrize(
    "latitude",
    [
        [(2, RATIONAL, [(36, 1), (48, 1)]), (1, ASCII, "N")],
        [(2, RATIONAL, [(36, 1)] * 4), (1, ASCII, "N")],
        [(2, ASCII, "36.8"), (1, ASCII, "N")],
        [(2, RATIONAL, [(36, 1), (48, 1), (0, 1)])],
    ],
)
def test_a_position_with_the_wrong_number_of_parts_or_the_wrong_kind_is_ignored(latitude):
    capture = capture_of(photo(gps_extra=latitude, longitude=(dms(10.1), "E")))

    assert capture is None


def test_the_cameras_own_accuracy_and_the_time_of_the_fix_are_read():
    gps_extra = [
        (0x1F, RATIONAL, [(125, 10)]),
        (7, RATIONAL, [(13, 1), (5, 1), (7, 1)]),
        (29, ASCII, "2026:09:30"),
    ]

    capture = capture_of(photo(latitude=TUNIS[0], longitude=TUNIS[1], gps_extra=gps_extra))

    assert capture is not None
    assert capture.accuracy_meters == 12.5
    assert capture.location_measured_at == datetime(2026, 9, 30, 13, 5, 7, tzinfo=UTC)


def test_an_unusable_accuracy_or_fix_time_is_left_out_but_the_position_stays():
    bad = [
        (0x1F, RATIONAL, [(1, 0)]),
        (7, RATIONAL, [(25, 1), (5, 1), (7, 1)]),
        (29, ASCII, "2026:09:30"),
    ]
    negative = [(0x1F, RATIONAL, [(0, 1)]), (7, RATIONAL, [(1, 1)]), (29, ASCII, "2026:09:30")]

    for extra in (bad, negative):
        capture = capture_of(photo(latitude=TUNIS[0], longitude=TUNIS[1], gps_extra=extra))
        assert capture is not None
        assert capture.has_location
        assert capture.accuracy_meters in (None, 0.0)
        assert capture.location_measured_at is None
    assert capture is not None
    assert capture.accuracy_meters == 0.0


@pytest.mark.parametrize(
    "stamp",
    [
        [(13, 1), (5, 1)],
        [(13, 1), (5, 1), (7, 1), (1, 1)],
        [(13, 0), (5, 1), (7, 1)],
    ],
)
def test_a_fix_time_that_is_not_hours_minutes_and_seconds_is_left_out(stamp):
    extra = [(7, RATIONAL, stamp), (29, ASCII, "2026:09:30")]

    capture = capture_of(photo(latitude=TUNIS[0], longitude=TUNIS[1], gps_extra=extra))

    assert capture is not None
    assert capture.has_location
    assert capture.location_measured_at is None


def test_a_fix_time_with_a_bad_date_is_left_out():
    extra = [(7, RATIONAL, [(13, 1), (5, 1), (7, 1)]), (29, ASCII, "2026:13:45")]

    capture = capture_of(photo(latitude=TUNIS[0], longitude=TUNIS[1], gps_extra=extra))

    assert capture is not None
    assert capture.location_measured_at is None


def test_the_fix_time_and_the_accuracy_are_not_reported_without_a_position():
    extra = [
        (0x1F, RATIONAL, [(125, 10)]),
        (7, RATIONAL, [(1, 1), (2, 1), (3, 1)]),
        (29, ASCII, "2026:09:30"),
    ]

    capture = capture_of(photo(gps_extra=extra, taken="2026:09:30 10:00:00"))

    assert capture is not None
    assert (capture.accuracy_meters, capture.location_measured_at) == (None, None)


# ─── The moment the photo was taken ───────────────────────────────────────────


def test_the_time_is_the_cameras_wall_clock_without_a_zone_when_the_file_names_none():
    capture = capture_of(photo(taken="2026:09:30 14:05:09"))

    assert capture is not None
    assert capture.captured_at == datetime(2026, 9, 30, 14, 5, 9)
    assert capture.captured_at.tzinfo is None
    assert not capture.has_location


def test_the_time_carries_its_utc_offset_when_the_file_gives_one():
    capture = capture_of(photo(taken="2026:09:30 14:05:09", offset="+01:00"))
    western = capture_of(photo(taken="2026:09:30 14:05:09", offset="-05:30"))

    assert capture is not None
    assert capture.captured_at == datetime(
        2026, 9, 30, 14, 5, 9, tzinfo=timezone(timedelta(hours=1))
    )
    assert western is not None
    assert western.captured_at.utcoffset() == -timedelta(hours=5, minutes=30)


@pytest.mark.parametrize("offset", ["", "Z", "+1:00", "+15:00", "+01:60", "one", "+01:00:00"])
def test_an_odd_offset_is_no_offset_rather_than_a_guess(offset):
    capture = capture_of(photo(taken="2026:09:30 14:05:09", offset=offset or None))

    assert capture is not None
    assert capture.captured_at.tzinfo is None


def test_the_digitised_time_is_used_when_there_is_no_original():
    capture = capture_of(photo(taken="2026:09:30 14:05:09", taken_tag=0x9004, offset="+02:00"))

    assert capture is not None
    assert capture.captured_at == datetime(
        2026, 9, 30, 14, 5, 9, tzinfo=timezone(timedelta(hours=2))
    )


def test_the_time_the_file_was_last_saved_is_not_when_it_was_taken():
    assert capture_of(photo(modified="2026:09:30 14:05:09")) is None


def test_no_date_is_no_date_and_never_the_time_of_the_upload(moving_clock):
    capture = capture_of(photo(latitude=TUNIS[0], longitude=TUNIS[1]))

    assert capture is not None
    assert capture.captured_at is None


@pytest.mark.parametrize(
    "stamp",
    [
        "0000:00:00 00:00:00",
        "    :  :     :  :  ",
        "2026:13:40 25:61:61",
        "not a date",
        "1970:01:01 00:00:00",
        "1989:12:31 23:59:59",
        # Two days and more ahead of the clock the tests run on.
        "2026:10:07 12:00:01",
    ],
)
def test_a_date_that_cannot_be_real_is_none(stamp, moving_clock):
    assert capture_of(photo(taken=stamp)) is None


def test_a_date_a_day_ahead_is_believed_for_a_time_zone_is_at_most_fourteen_hours(moving_clock):
    capture = capture_of(photo(taken="2026:10:05 12:00:00"))

    assert capture is not None
    assert capture.captured_at == datetime(2026, 10, 5, 12, 0, 0)


def test_a_date_with_a_nul_after_it_is_still_read():
    capture = capture_of(photo(taken="2026:09:30 14:05:09\x00"))

    assert capture is not None
    assert capture.captured_at == datetime(2026, 9, 30, 14, 5, 9)


def test_a_photo_with_no_exif_has_no_capture_metadata():
    assert process_photo(jpeg_of(pixels())).capture is None


# Pillow itself warns about corrupt EXIF when it opens the file; in production that is a line on
# stderr, and the test keeps it a warning too, since what it checks is that the photo still goes
# through.
@pytest.mark.filterwarnings("ignore:Corrupt EXIF data")
def test_a_photo_whose_exif_is_broken_still_processes_and_says_nothing_but_the_error_type(caplog):
    broken = with_segment(jpeg_of(pixels()), 0xE1, b"Exif\x00\x00" + b"II*\x00\xff\xff\xff\x7f")

    with caplog.at_level(logging.WARNING, logger="tabsira.images"):
        processed = process_photo(broken)

    assert processed.capture is None
    assert_no_metadata(processed.data)
    assert caplog.text.count("EXIF could not be read") <= 1


def test_an_image_whose_exif_cannot_be_read_has_no_capture_metadata_and_logs_only_the_type(caplog):
    class Unreadable:
        def getexif(self):
            raise ValueError("secret detail: 36.8, 10.18")

    with caplog.at_level(logging.WARNING, logger="tabsira.images"):
        assert read_capture_metadata(Unreadable()) is None  # type: ignore[arg-type]

    assert "ValueError" in caplog.text
    assert "secret detail" not in caplog.text


def test_capture_metadata_never_prints_its_position_or_times():
    capture = CaptureMetadata(
        latitude=36.8065,
        longitude=10.1815,
        accuracy_meters=12.5,
        captured_at=datetime(2026, 9, 30, 14, 5, 9),
        location_measured_at=datetime(2026, 9, 30, 13, 5, 7, tzinfo=UTC),
    )
    processed = process_photo(photo(latitude=TUNIS[0], longitude=TUNIS[1]))

    for shown in (repr(capture), repr(processed), str(processed)):
        for value in ("36.8", "10.18", "12.5", "2026", "14:05"):
            assert value not in shown
    assert "photo_exif" in repr(capture)


# ─── What comes out ───────────────────────────────────────────────────────────


def test_what_comes_out_has_no_metadata_of_any_kind_though_the_input_had_all_of_it():
    original = photo(
        latitude=TUNIS[0],
        longitude=TUNIS[1],
        taken="2026:09:30 14:05:09",
        offset="+01:00",
        orientation=1,
        gps_extra=[(0x1F, RATIONAL, [(125, 10)])],
    )
    # The input really does carry what the output must not.
    for present in (b"Exif", b"http://ns.adobe.com", b"ICC_PROFILE", b"Photoshop", b"TestCamera"):
        assert present in original
    assert SECRET_COMMENT in original
    assert SECRET_SERIAL.encode() in original

    processed = process_photo(original)

    assert processed.capture is not None
    assert processed.capture.has_location
    assert_no_metadata(processed.data)
    assert processed.content_type == "image/jpeg"
    assert (processed.width, processed.height) == (64, 48)
    assert Image.open(io.BytesIO(processed.data)).format == "JPEG"


@pytest.mark.parametrize("big_endian", [False, True])
def test_the_gps_position_is_in_the_capture_and_not_in_the_image_in_either_byte_order(big_endian):
    processed = process_photo(photo(big_endian=big_endian, latitude=SYDNEY[0], longitude=SYDNEY[1]))

    assert processed.capture is not None
    assert processed.capture.latitude == pytest.approx(-33.8688, abs=1e-3)
    exif = Image.open(io.BytesIO(processed.data)).getexif()
    assert exif.get_ifd(ExifTags.IFD.GPSInfo) == {}
    assert_no_metadata(processed.data)


def test_the_pixels_are_kept_closely():
    source = pixels((64, 48))
    processed = process_photo(jpeg_of(source))

    out = Image.open(io.BytesIO(processed.data)).convert("RGB")
    for point in ((0, 0), (63, 0), (0, 47), (63, 47), (32, 24)):
        assert all(
            abs(a - b) <= 12
            for a, b in zip(out.getpixel(point), source.getpixel(point), strict=True)
        )


@pytest.mark.parametrize(
    ("orientation", "size", "corner_after"),
    [
        (1, (64, 48), (0, 0)),
        (3, (64, 48), (63, 47)),
        (6, (48, 64), (47, 0)),
        (8, (48, 64), (0, 63)),
    ],
)
def test_the_photo_is_turned_upright_and_the_orientation_tag_goes(orientation, size, corner_after):
    source = pixels((64, 48), marker=True)
    data = with_exif(jpeg_of(source), exif_block(orientation=orientation))

    processed = process_photo(data)

    out = Image.open(io.BytesIO(processed.data)).convert("RGB")
    assert out.size == size == (processed.width, processed.height)
    red, _green, blue = out.getpixel(corner_after)
    assert red > 200 and blue < 80
    assert 274 not in out.getexif()


def test_a_big_photo_is_shrunk_to_the_longer_side_limit_keeping_its_shape():
    processed = process_photo(jpeg_of(pixels((4000, 3000))))

    assert (processed.width, processed.height) == (2560, 1920)


def test_a_small_photo_is_never_enlarged():
    processed = process_photo(jpeg_of(pixels((100, 80))))

    assert (processed.width, processed.height) == (100, 80)


def test_an_embedded_colour_profile_is_applied_and_then_dropped():
    data = with_everything(jpeg_of(pixels()))
    assert b"ICC_PROFILE" in data

    processed = process_photo(data)

    assert "icc_profile" not in Image.open(io.BytesIO(processed.data)).info
    assert_no_metadata(processed.data)


def test_the_profile_is_converted_with_the_colour_engine(monkeypatch):
    calls: list[str] = []
    real = ImageCms.profileToProfile

    def spy(image, source, target, **options):
        calls.append(options["outputMode"])
        return real(image, source, target, **options)

    monkeypatch.setattr(ImageCms, "profileToProfile", spy)

    process_photo(with_everything(jpeg_of(pixels())))

    assert calls == ["RGB"]


@pytest.mark.parametrize("profile", [b"not a profile at all", b"\x00" * 200, b""])
def test_a_broken_colour_profile_is_dropped_and_the_pixels_taken_as_srgb(profile, caplog):
    data = with_segment(jpeg_of(pixels()), 0xE2, b"ICC_PROFILE\x00\x01\x01" + profile)

    with caplog.at_level(logging.WARNING, logger="tabsira.images"):
        processed = process_photo(data)

    assert_no_metadata(processed.data)
    assert (processed.width, processed.height) == (64, 48)


def test_a_profile_for_another_colour_space_is_dropped_too(caplog):
    lab = ImageCms.ImageCmsProfile(ImageCms.createProfile("LAB")).tobytes()
    data = with_segment(jpeg_of(pixels()), 0xE2, b"ICC_PROFILE\x00\x01\x01" + lab)

    with caplog.at_level(logging.WARNING, logger="tabsira.images"):
        processed = process_photo(data)

    assert "colour profile could not be applied" in caplog.text
    assert_no_metadata(processed.data)


def test_a_profile_that_converts_to_nothing_leaves_the_plain_pixels(monkeypatch):
    monkeypatch.setattr(ImageCms, "profileToProfile", lambda *_a, **_k: None)

    processed = process_photo(with_everything(jpeg_of(pixels())))

    assert_no_metadata(processed.data)


# ─── Other formats ────────────────────────────────────────────────────────────


def png_of(image: Image.Image, **options: object) -> bytes:
    out = io.BytesIO()
    image.save(out, "PNG", **options)
    return out.getvalue()


def test_a_png_with_a_gps_exif_chunk_is_read_and_comes_out_as_a_clean_jpeg():
    exif = Image.Exif()
    gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
    gps[1], gps[2], gps[3], gps[4] = "N", (36.0, 48.0, 23.4), "E", (10.0, 10.0, 53.4)
    exif[ExifTags.Base.GPSInfo] = gps
    data = png_of(pixels(), exif=exif)

    processed = process_photo(data)

    assert processed.capture is not None
    assert processed.capture.latitude == pytest.approx(36.8065, abs=1e-3)
    assert_no_metadata(processed.data)


def test_a_png_with_text_chunks_loses_them():
    from PIL import PngImagePlugin

    info = PngImagePlugin.PngInfo()
    info.add_text("Author", "Private Person")
    info.add_itxt("XML:com.adobe.xmp", SECRET_XMP.decode())

    processed = process_photo(png_of(pixels(), pnginfo=info))

    assert b"Private Person" not in processed.data
    assert_no_metadata(processed.data)


def test_a_webp_with_exif_is_read_and_comes_out_as_a_clean_jpeg():
    exif = Image.Exif()
    gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
    gps[1], gps[2], gps[3], gps[4] = "S", (33.0, 52.0, 7.7), "E", (151.0, 12.0, 33.5)
    exif[ExifTags.Base.GPSInfo] = gps
    out = io.BytesIO()
    pixels().save(out, "WEBP", exif=exif)

    processed = process_photo(out.getvalue())

    assert processed.capture is not None
    assert processed.capture.latitude == pytest.approx(-33.8688, abs=1e-3)
    assert_no_metadata(processed.data)


def test_transparency_is_flattened_onto_white():
    rgba = Image.new("RGBA", (64, 64), (255, 0, 0, 0))
    rgba.paste((0, 0, 255, 255), (0, 0, 24, 24))

    out = Image.open(io.BytesIO(process_photo(png_of(rgba)).data)).convert("RGB")

    # The transparent area is white, whatever colour its hidden pixels had; opaque stays opaque.
    assert min(out.getpixel((50, 50))) > 240
    red, green, blue = out.getpixel((8, 8))
    assert blue > 200 and red < 60 and green < 60


def test_a_palette_image_with_a_transparent_colour_is_flattened_onto_white():
    palette = Image.new("P", (16, 16), 0)
    palette.putpalette([255, 0, 0, 0, 0, 255] + [0] * 250 * 3)

    out = Image.open(io.BytesIO(process_photo(png_of(palette, transparency=0)).data)).convert("RGB")

    assert min(out.getpixel((8, 8))) > 240


def test_a_grayscale_and_a_cmyk_photo_become_plain_rgb():
    gray = Image.open(io.BytesIO(process_photo(jpeg_of(pixels(mode="L"))).data))
    cmyk_source = io.BytesIO()
    pixels().convert("CMYK").save(cmyk_source, "JPEG")
    cmyk = Image.open(io.BytesIO(process_photo(cmyk_source.getvalue()).data))

    assert gray.mode == cmyk.mode == "RGB"


# ─── What is refused ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"", "unreadable"),
        (b"not an image at all", "unreadable"),
        (b"\xff\xd8\xff\xe0 truncated", "unreadable"),
        (b"%PDF-1.7 ...", "unreadable"),
        (b"<svg xmlns='http://www.w3.org/2000/svg'/>", "unreadable"),
    ],
)
def test_what_is_not_a_photo_is_refused_with_a_reason(data, reason):
    with pytest.raises(ImageRejectedError) as caught:
        process_photo(data)

    assert caught.value.reason == reason


@pytest.mark.parametrize("format_", ["GIF", "BMP", "TIFF"])
def test_a_format_that_is_not_accepted_is_unsupported(format_):
    out = io.BytesIO()
    pixels((8, 8)).save(out, format_)

    with pytest.raises(ImageRejectedError) as caught:
        process_photo(out.getvalue())

    assert caught.value.reason == "unsupported"


def test_a_file_over_the_byte_limit_is_refused_without_being_read():
    with pytest.raises(ImageRejectedError) as caught:
        process_photo(b"\xff\xd8" + bytes(image_service.MAX_INPUT_BYTES))

    assert caught.value.reason == "too_large"


def test_a_picture_with_too_many_pixels_is_refused_before_it_is_decoded():
    huge = Image.new("1", (8000, 7000))  # 56 megapixels, a few hundred bytes as a PNG

    with pytest.raises(ImageRejectedError) as caught:
        process_photo(png_of(huge))

    assert caught.value.reason == "too_many_pixels"


def test_a_decompression_bomb_is_refused(monkeypatch):
    def bomb(_stream):
        raise Image.DecompressionBombError("too big")

    monkeypatch.setattr(Image, "open", bomb)

    with pytest.raises(ImageRejectedError) as caught:
        process_photo(b"x")

    assert caught.value.reason == "too_many_pixels"


def test_a_photo_that_fails_to_decode_after_opening_is_unreadable():
    good = jpeg_of(pixels((200, 200)))
    cut = good[: len(good) // 2]

    with pytest.raises(ImageRejectedError) as caught:
        process_photo(cut)

    assert caught.value.reason == "unreadable"


def test_the_refusal_message_is_only_the_reason():
    assert str(ImageRejectedError("unsupported")) == "unsupported"


# ─── Off the event loop ───────────────────────────────────────────────────────


async def test_the_work_can_be_done_in_a_thread():
    processed = await process_photo_in_thread(photo(latitude=TUNIS[0], longitude=TUNIS[1]))

    assert processed.capture is not None
    assert_no_metadata(processed.data)
