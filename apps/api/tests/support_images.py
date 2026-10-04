"""
Photos for the image tests, built byte by byte so no library writes what another one reads.

`Pillow` makes the pixels. The EXIF block is written here with `struct`, in either byte order,
the way a camera writes it: an IFD0 that points at an Exif IFD and a GPS IFD. The other kinds of
metadata a phone embeds (XMP, IPTC, an ICC profile, a comment, a maker note, serial numbers) are
added as raw JPEG segments, so a test can look for exactly those bytes in what comes out.
"""

from __future__ import annotations

import io
import struct
from typing import Any

from PIL import Image, ImageCms

# A string that appears in a file only in metadata. The tests look for it in the output.
SECRET_SERIAL = "SERIAL-8841-5527"
SECRET_MAKER_NOTE = b"MAKERNOTE-private-bytes-9921"
SECRET_COMMENT = b"comment: taken at the owner's home"
SECRET_XMP = b"<x:xmpmeta><rdf:li>XMP-creator-private-name</rdf:li></x:xmpmeta>"

ASCII, SHORT, LONG, RATIONAL, UNDEFINED = 2, 3, 4, 5, 7
_SIZES = {ASCII: 1, SHORT: 2, LONG: 4, RATIONAL: 8, UNDEFINED: 1}

Entry = tuple[int, int, Any]


def _encode(order: str, kind: int, value: Any) -> tuple[int, bytes]:
    """Return the element count and the bytes of one entry's value."""
    if kind == ASCII:
        data = value.encode() + b"\x00"
        return len(data), data
    if kind == UNDEFINED:
        return len(value), value
    values = value if isinstance(value, list) else [value]
    if kind == SHORT:
        return len(values), b"".join(struct.pack(order + "H", v) for v in values)
    if kind == LONG:
        return len(values), b"".join(struct.pack(order + "I", v) for v in values)
    return len(values), b"".join(struct.pack(order + "II", n, d) for n, d in values)


def _table_size(order: str, entries: list[Entry]) -> int:
    extra = 0
    for _tag, kind, value in entries:
        _count, data = _encode(order, kind, value)
        extra += len(data) + len(data) % 2 if len(data) > 4 else 0
    return 2 + 12 * len(entries) + 4 + extra


def _table(order: str, entries: list[Entry], offset: int) -> bytes:
    """Write one IFD whose first byte lies at `offset` of the TIFF block."""
    entries = sorted(entries, key=lambda entry: entry[0])
    head = struct.pack(order + "H", len(entries))
    data_at = offset + 2 + 12 * len(entries) + 4
    body, extra = b"", b""
    for tag, kind, value in entries:
        count, data = _encode(order, kind, value)
        if len(data) <= 4:
            cell = data.ljust(4, b"\x00")
        else:
            cell = struct.pack(order + "I", data_at + len(extra))
            extra += data + (b"\x00" if len(data) % 2 else b"")
        body += struct.pack(order + "HHI", tag, kind, count) + cell
    return head + body + struct.pack(order + "I", 0) + extra


def rational(value: float) -> tuple[int, int]:
    return round(value * 10_000), 10_000


def dms(degrees: float) -> list[tuple[int, int]]:
    """Degrees as the three rationals EXIF uses: whole degrees, whole minutes, seconds."""
    # In units of a ten-thousandth of an arc-second, so no float noise makes 48' into 47'60".
    total = round(degrees * 3600 * 10_000)
    whole, rest = divmod(total, 3600 * 10_000)
    minutes, units = divmod(rest, 60 * 10_000)
    return [(whole, 1), (minutes, 1), (units, 10_000)]


def exif_block(
    *,
    big_endian: bool = False,
    latitude: tuple[list[tuple[int, int]], str] | None = None,
    longitude: tuple[list[tuple[int, int]], str] | None = None,
    gps_extra: list[Entry] | None = None,
    taken: str | None = None,
    taken_tag: int = 0x9003,
    offset: str | None = None,
    modified: str | None = None,
    orientation: int | None = None,
    private: bool = True,
) -> bytes:
    """Build the TIFF block that follows `Exif\\0\\0` in an APP1 segment."""
    order = ">" if big_endian else "<"
    ifd0: list[Entry] = []
    details: list[Entry] = []
    gps: list[Entry] = list(gps_extra or [])
    if private:
        ifd0.append((0x010F, ASCII, "TestCamera Inc."))
        ifd0.append((0x0110, ASCII, "Model X"))
        details.append((0x927C, UNDEFINED, SECRET_MAKER_NOTE))
        details.append((0xA431, ASCII, SECRET_SERIAL))
    if orientation is not None:
        ifd0.append((0x0112, SHORT, orientation))
    if modified is not None:
        ifd0.append((0x0132, ASCII, modified))
    if taken is not None:
        details.append((taken_tag, ASCII, taken))
    if offset is not None:
        details.append((0x9011 if taken_tag == 0x9003 else 0x9012, ASCII, offset))
    if latitude is not None:
        gps += [(1, ASCII, latitude[1]), (2, RATIONAL, latitude[0])]
    if longitude is not None:
        gps += [(3, ASCII, longitude[1]), (4, RATIONAL, longitude[0])]

    has_exif, has_gps = bool(details), bool(gps)
    # An IFD's size does not depend on its values, so the pointers can be measured first.
    placeholders: list[Entry] = [(0x8769, LONG, 0)] * has_exif + [(0x8825, LONG, 0)] * has_gps
    exif_at = 8 + _table_size(order, [*ifd0, *placeholders])
    gps_at = exif_at + (_table_size(order, details) if has_exif else 0)
    pointers: list[Entry] = [(0x8769, LONG, exif_at)] * has_exif + [
        (0x8825, LONG, gps_at)
    ] * has_gps
    ifd0_bytes = _table(order, [*ifd0, *pointers], 8)
    header = (b"MM\x00*" if big_endian else b"II*\x00") + struct.pack(order + "I", 8)
    block = header + ifd0_bytes
    if has_exif:
        block += _table(order, details, len(block))
    if has_gps:
        block += _table(order, gps, len(block))
    return block


def pixels(
    size: tuple[int, int] = (64, 48), mode: str = "RGB", marker: bool = False
) -> Image.Image:
    """A gradient, so colours can be compared; with `marker`, a red square in the top-left."""
    width, height = size
    image = Image.new("RGB", size)
    image.putdata(
        [
            (x * 255 // max(width - 1, 1), y * 255 // max(height - 1, 1), 128)
            for y in range(height)
            for x in range(width)
        ]
    )
    if marker:
        for y in range(min(8, height)):
            for x in range(min(8, width)):
                image.putpixel((x, y), (255, 0, 0))
    return image if mode == "RGB" else image.convert(mode)


def jpeg_of(image: Image.Image, **options: Any) -> bytes:
    out = io.BytesIO()
    image.save(out, "JPEG", quality=95, **options)
    return out.getvalue()


def with_segment(jpeg: bytes, marker: int, payload: bytes) -> bytes:
    """Insert one marker segment right after the start-of-image marker."""
    segment = bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload
    return jpeg[:2] + segment + jpeg[2:]


def with_exif(jpeg: bytes, block: bytes) -> bytes:
    return with_segment(jpeg, 0xE1, b"Exif\x00\x00" + block)


def with_everything(jpeg: bytes) -> bytes:
    """Add what a phone embeds besides EXIF: XMP, a comment, an IPTC record and an ICC profile."""
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    jpeg = with_segment(jpeg, 0xE1, b"http://ns.adobe.com/xap/1.0/\x00" + SECRET_XMP)
    jpeg = with_segment(jpeg, 0xFE, SECRET_COMMENT)
    jpeg = with_segment(jpeg, 0xED, b"Photoshop 3.0\x008BIM\x04\x04\x00\x00\x00\x00IPTC-keywords")
    return with_segment(jpeg, 0xE2, b"ICC_PROFILE\x00\x01\x01" + profile)


def marker_codes(jpeg: bytes) -> list[int]:
    """The marker segments before the image data, in order (SOI and EOI left out)."""
    codes: list[int] = []
    position = 2
    while position < len(jpeg) - 1:
        marker = jpeg[position + 1]
        codes.append(marker)
        if marker == 0xDA:
            break
        position += 2 + struct.unpack(">H", jpeg[position + 2 : position + 4])[0]
    return codes
