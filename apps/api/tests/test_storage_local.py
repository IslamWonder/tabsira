"""Photo storage keys, and the local-disk store: nothing guessable, nothing half-written."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from src.storage import base, local
from src.storage.base import (
    InvalidKeyError,
    InvalidTtlError,
    ObjectNotFoundError,
    StorageError,
    check_key,
    is_public_key,
    new_key,
    new_private_key,
    new_public_key,
)
from src.storage.local import LocalStorage, default_media_root

REPO_ROOT = Path(__file__).resolve().parents[3]
JPEG = b"\xff\xd8\xff\xe0 not really a photo \xff\xd9"
OTHER = b"\xff\xd8\xff\xe0 another \xff\xd9"
API = "https://api.tabsira.test"


@pytest.fixture
def store(tmp_path: Path) -> LocalStorage:
    return LocalStorage(
        tmp_path / "media", base_url=API, signing_key=b"k" * 32, default_ttl_seconds=300
    )


# ─── Keys ─────────────────────────────────────────────────────────────────────


def test_a_key_is_a_prefix_and_128_random_bits_in_hex():
    private, public = new_private_key(), new_public_key()

    assert re.fullmatch(r"private/[0-9a-f]{32}\.jpg", private)
    assert re.fullmatch(r"public/[0-9a-f]{32}\.jpg", public)
    assert not is_public_key(private)
    assert is_public_key(public)


def test_keys_do_not_repeat_and_do_not_share_an_id_between_the_two_prefixes():
    keys = [new_private_key() for _ in range(2000)] + [new_public_key() for _ in range(2000)]

    assert len(set(keys)) == 4000
    assert len({key.split("/")[1] for key in keys}) == 4000


def test_an_unknown_prefix_makes_no_key():
    with pytest.raises(InvalidKeyError):
        new_key("secret")


@pytest.mark.parametrize(
    "key",
    [
        "",
        "../etc/passwd",
        "private/../../etc/passwd",
        "private/" + "a" * 32,
        "private/" + "a" * 32 + ".png",
        "private/" + "a" * 31 + ".jpg",
        "private/" + "a" * 33 + ".jpg",
        "private/" + "A" * 32 + ".jpg",
        "private/" + "g" * 32 + ".jpg",
        "/private/" + "a" * 32 + ".jpg",
        "other/" + "a" * 32 + ".jpg",
        "private/ab/" + "a" * 32 + ".jpg",
        "private/" + "a" * 32 + ".jpg\n",
        "private/" + "a" * 32 + ".jpg\x00",
        "public\\" + "a" * 32 + ".jpg",
    ],
)
def test_only_a_key_made_here_is_a_key(key):
    with pytest.raises(InvalidKeyError):
        check_key(key)
    with pytest.raises(InvalidKeyError):
        is_public_key(key)
    assert issubclass(InvalidKeyError, StorageError)
    assert issubclass(InvalidKeyError, ValueError)


@pytest.mark.parametrize(
    ("data", "content_type"),
    [
        (b"", "image/jpeg"),
        (JPEG, "image/png"),
        (JPEG, "text/html"),
        (bytes(20 * 1024 * 1024 + 1), "image/jpeg"),
    ],
)
def test_only_a_bounded_jpeg_object_is_accepted(data, content_type):
    with pytest.raises(InvalidKeyError):
        base.check_object(new_private_key(), data, content_type)

    base.check_object(new_private_key(), JPEG, "image/jpeg")
    base.check_object(new_private_key(), bytes(20 * 1024 * 1024), "image/jpeg")


# ─── Objects ──────────────────────────────────────────────────────────────────


async def test_an_object_is_stored_and_read_back_byte_for_byte(store):
    key = new_private_key()

    await store.put(key, JPEG)

    assert await store.get(key) == JPEG
    assert await store.exists(key)


async def test_the_file_lies_under_the_media_folder_with_a_fan_out_folder_and_owner_only_rights(
    store,
):
    key = new_private_key()
    identifier = key.split("/")[1].removesuffix(".jpg")

    await store.put(key, JPEG)

    path = store.root / "private" / identifier[:2] / f"{identifier}.jpg"
    assert path.read_bytes() == JPEG
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) & 0o077 == 0
    # Nothing else was left behind: no temporary file.
    assert [p.name for p in path.parent.iterdir()] == [path.name]


async def test_a_second_put_replaces_the_object(store):
    key = new_private_key()
    await store.put(key, JPEG)

    await store.put(key, OTHER)

    assert await store.get(key) == OTHER


async def test_a_missing_object_is_not_found_and_does_not_exist(store):
    key = new_private_key()

    assert not await store.exists(key)
    with pytest.raises(ObjectNotFoundError):
        await store.get(key)
    assert issubclass(ObjectNotFoundError, LookupError)


async def test_deleting_removes_the_object_and_deleting_again_is_fine(store):
    key = new_private_key()
    await store.put(key, JPEG)

    await store.delete(key)
    await store.delete(key)

    assert not await store.exists(key)


async def test_a_copy_is_a_second_object_that_outlives_the_first(store):
    source, destination = new_private_key(), new_public_key()
    await store.put(source, JPEG)

    await store.copy(source, destination)
    await store.delete(source)

    assert await store.get(destination) == JPEG


async def test_copying_what_is_not_there_is_not_found(store):
    with pytest.raises(ObjectNotFoundError):
        await store.copy(new_private_key(), new_public_key())
    assert not await store.exists(new_public_key())


async def test_a_refused_object_leaves_no_file(store):
    with pytest.raises(InvalidKeyError):
        await store.put(new_private_key(), b"")
    with pytest.raises(InvalidKeyError):
        await store.put("private/../../x.jpg", JPEG)

    assert not store.root.exists()


@pytest.mark.parametrize("method", ["get", "exists", "delete"])
async def test_a_key_that_is_not_one_never_reaches_the_disk(store, method):
    with pytest.raises(InvalidKeyError):
        await getattr(store, method)("../../etc/passwd")


async def test_a_failed_write_leaves_the_old_object_and_no_temporary_file(store, monkeypatch):
    key = new_private_key()
    await store.put(key, JPEG)

    def explode(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "fdopen", explode)
    with pytest.raises(OSError, match="disk full"):
        await store.put(key, OTHER)
    monkeypatch.undo()

    assert await store.get(key) == JPEG
    folder = next((store.root / "private").iterdir())
    assert [p.name for p in folder.iterdir()] == [key.split("/")[1]]


def test_the_media_folder_is_data_media_of_the_checkout_and_is_not_tracked():
    assert default_media_root() == REPO_ROOT / "data" / "media"
    ignored = (REPO_ROOT / ".gitignore").read_text().splitlines()
    assert "data/media/" in ignored


def test_outside_a_checkout_the_folder_is_under_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(local, "_ROOT_MARKER", "no-such-marker-file")
    monkeypatch.chdir(tmp_path)

    assert default_media_root() == tmp_path / "data" / "media"


# ─── Addresses ────────────────────────────────────────────────────────────────


def parts(url: str) -> tuple[str, dict[str, str]]:
    split = urlsplit(url)
    query = {name: values[0] for name, values in parse_qs(split.query).items()}
    return f"{split.scheme}://{split.netloc}{split.path}", query


def test_a_signed_link_names_the_key_an_expiry_and_a_signature(store, moving_clock):
    key = new_private_key()

    address, query = parts(store.signed_url(key))

    assert address == f"{API}/media/{key}"
    assert int(query["expires"]) == int(moving_clock.now.timestamp()) + 300
    assert re.fullmatch(r"[0-9a-f]{64}", query["signature"])
    assert store.verify_signature(key, int(query["expires"]), query["signature"])


def test_a_link_may_ask_for_a_shorter_life(store, moving_clock):
    _, query = parts(store.signed_url(new_private_key(), ttl_seconds=60))

    assert int(query["expires"]) == int(moving_clock.now.timestamp()) + 60


def test_a_link_stops_working_when_it_expires(store, moving_clock):
    key = new_private_key()
    _, query = parts(store.signed_url(key))
    expires, signature = int(query["expires"]), query["signature"]

    moving_clock.advance(seconds=300)
    assert store.verify_signature(key, expires, signature)
    moving_clock.advance(seconds=1)
    assert not store.verify_signature(key, expires, signature)


def test_a_link_cannot_be_changed_or_moved_to_another_photo_or_installation(store, moving_clock):
    key, other = new_private_key(), new_private_key()
    _, query = parts(store.signed_url(key))
    expires, signature = int(query["expires"]), query["signature"]
    elsewhere = LocalStorage(
        store.root, base_url=API, signing_key=b"j" * 32, default_ttl_seconds=300
    )

    assert not store.verify_signature(key, expires + 1000, signature)
    assert not store.verify_signature(other, expires, signature)
    # A different last character, whatever the real one is (a fixed "0" matched one link in 16).
    tampered = signature[:-1] + ("1" if signature.endswith("0") else "0")
    assert not store.verify_signature(key, expires, tampered)
    assert not store.verify_signature(key, expires, "")
    assert not elsewhere.verify_signature(key, expires, signature)
    assert not store.verify_signature("../x", expires, signature)


def test_a_link_lives_at_least_a_second_and_at_most_an_hour(store):
    assert store.signed_url(new_private_key(), ttl_seconds=3600)
    for bad in (0, -5, 3601):
        with pytest.raises(InvalidTtlError):
            store.signed_url(new_private_key(), ttl_seconds=bad)


def test_no_link_is_made_for_what_is_not_a_key(store):
    with pytest.raises(InvalidKeyError):
        store.signed_url("../etc/passwd")


def test_only_a_published_copy_has_a_public_address(store):
    public, private = new_public_key(), new_private_key()

    assert store.public_url(public) == f"{API}/media/{public}"
    with pytest.raises(InvalidKeyError):
        store.public_url(private)
    with pytest.raises(InvalidKeyError):
        store.public_url("../etc/passwd")
