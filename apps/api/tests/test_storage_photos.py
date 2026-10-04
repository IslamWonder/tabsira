"""Who may have a photo kept, and the proof that a refusal writes nothing."""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from typing import Any

import pytest
from PIL import ExifTags, Image

from src.models.profile import AgeRange
from src.services.image_service import ProcessedPhoto, process_photo
from src.storage.base import InvalidKeyError, ObjectNotFoundError, new_private_key, new_public_key
from src.storage.local import LocalStorage
from src.storage.photos import (
    PhotoFacts,
    PhotoNotAllowedError,
    PhotoRefusal,
    PhotoStore,
    build_photo_store,
)
from tests.support_images import dms, exif_block, jpeg_of, pixels, with_everything, with_exif

OWNER = uuid.UUID("0199b6a0-0000-7000-8000-000000000001")
CLEAN = jpeg_of(pixels())


def facts(**values: Any) -> PhotoFacts:
    return PhotoFacts(
        **{
            "owner_id": OWNER,
            "age_range": AgeRange.FROM_25_TO_39,
            "sensitive_scene": False,
            "photo_storage_consent": True,
            **values,
        }
    )


def photo() -> ProcessedPhoto:
    return ProcessedPhoto(data=CLEAN, width=64, height=48, capture=None)


class Untouchable:
    """A store that fails the test if anything at all is asked of it."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the storage was asked for {name}")


@pytest.fixture
def disk(tmp_path: Path) -> LocalStorage:
    return LocalStorage(
        tmp_path / "media",
        base_url="https://api.tabsira.test",
        signing_key=b"k" * 32,
        default_ttl_seconds=300,
    )


@pytest.fixture
def photos(disk: LocalStorage, make_settings) -> PhotoStore:
    return PhotoStore(disk, make_settings())


# ─── The facts a caller must state ────────────────────────────────────────────


def test_every_fact_is_required_by_keyword_so_none_can_be_forgotten():
    with pytest.raises(TypeError):
        PhotoFacts(owner_id=OWNER)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        PhotoFacts(OWNER, AgeRange.UNKNOWN, False, True)  # type: ignore[misc]
    with pytest.raises(TypeError):
        PhotoFacts(  # type: ignore[call-arg]
            age_range=AgeRange.UNKNOWN, sensitive_scene=False, photo_storage_consent=True
        )


def test_a_signed_in_adult_who_agreed_with_an_ordinary_scene_may_keep_a_photo(make_settings):
    assert facts().refusal(make_settings()) is None


@pytest.mark.parametrize(
    "age", [a for a in AgeRange if a is not AgeRange.UNDER_13], ids=lambda a: a.value
)
def test_any_age_but_under_13_is_allowed_and_an_unanswered_age_is_never_guessed(age, make_settings):
    assert facts(age_range=age).refusal(make_settings()) is None


@pytest.mark.parametrize(
    ("values", "reason"),
    [
        ({"owner_id": None}, PhotoRefusal.GUEST),
        ({"age_range": AgeRange.UNDER_13}, PhotoRefusal.UNDER_13),
        ({"sensitive_scene": True}, PhotoRefusal.SENSITIVE_SCENE),
        ({"photo_storage_consent": False}, PhotoRefusal.NO_CONSENT),
    ],
)
def test_each_reason_alone_refuses(values, reason, make_settings):
    assert facts(**values).refusal(make_settings()) is reason


def test_a_switched_off_feature_refuses_everyone(make_settings):
    assert facts().refusal(make_settings(feature_photo_storage=False)) is PhotoRefusal.FEATURE_OFF


def test_when_several_reasons_hold_the_first_in_order_is_given(make_settings):
    everything = facts(
        owner_id=None,
        age_range=AgeRange.UNDER_13,
        sensitive_scene=True,
        photo_storage_consent=False,
    )

    assert (
        everything.refusal(make_settings(feature_photo_storage=False)) is PhotoRefusal.FEATURE_OFF
    )
    assert everything.refusal(make_settings()) is PhotoRefusal.GUEST
    assert (
        facts(
            age_range=AgeRange.UNDER_13, sensitive_scene=True, photo_storage_consent=False
        ).refusal(make_settings())
        is PhotoRefusal.UNDER_13
    )
    assert (
        facts(sensitive_scene=True, photo_storage_consent=False).refusal(make_settings())
        is PhotoRefusal.SENSITIVE_SCENE
    )


# ─── Refusals write nothing ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("values", "reason"),
    [
        ({"owner_id": None}, PhotoRefusal.GUEST),
        ({"age_range": AgeRange.UNDER_13}, PhotoRefusal.UNDER_13),
        ({"sensitive_scene": True}, PhotoRefusal.SENSITIVE_SCENE),
        ({"photo_storage_consent": False}, PhotoRefusal.NO_CONSENT),
    ],
)
async def test_a_refused_photo_is_not_kept_and_the_storage_is_never_asked(
    values, reason, make_settings
):
    store = PhotoStore(Untouchable(), make_settings())  # type: ignore[arg-type]

    with pytest.raises(PhotoNotAllowedError) as caught:
        await store.keep(facts(**values), photo())

    assert caught.value.reason is reason
    assert str(caught.value) == reason.value


async def test_a_photo_is_not_kept_while_the_feature_is_off(make_settings):
    store = PhotoStore(Untouchable(), make_settings(feature_photo_storage=False))  # type: ignore[arg-type]

    with pytest.raises(PhotoNotAllowedError) as caught:
        await store.keep(facts(), photo())

    assert caught.value.reason is PhotoRefusal.FEATURE_OFF


@pytest.mark.parametrize(
    "values",
    [
        {"owner_id": None},
        {"age_range": AgeRange.UNDER_13},
        {"sensitive_scene": True},
        {"photo_storage_consent": False},
    ],
)
async def test_a_refused_photo_is_not_published_either_and_nothing_is_copied(
    values, make_settings, photos, disk
):
    kept = await photos.keep(facts(), photo())

    with pytest.raises(PhotoNotAllowedError):
        await photos.publish(facts(**values), kept.key)

    assert not (disk.root / "public").exists()


async def test_the_folder_stays_empty_after_every_refusal(photos, disk):
    for values in (
        {"owner_id": None},
        {"age_range": AgeRange.UNDER_13},
        {"sensitive_scene": True},
        {"photo_storage_consent": False},
    ):
        with pytest.raises(PhotoNotAllowedError):
            await photos.keep(facts(**values), photo())

    assert not disk.root.exists()


# ─── Keeping, publishing, withdrawing ─────────────────────────────────────────


async def test_a_kept_photo_is_the_clean_image_under_a_random_private_key(photos, disk):
    stored = await photos.keep(facts(), photo())

    assert stored.key.startswith("private/")
    assert (stored.width, stored.height) == (64, 48)
    assert await disk.get(stored.key) == CLEAN


async def test_two_photos_get_two_keys_that_say_nothing_about_each_other_or_the_owner(photos):
    first = await photos.keep(facts(), photo())
    second = await photos.keep(facts(), photo())

    assert first.key != second.key
    assert str(OWNER).replace("-", "") not in first.key


async def test_what_is_kept_has_no_gps_though_the_photo_that_came_in_had_it(photos, disk):
    original = with_everything(
        with_exif(
            jpeg_of(pixels()),
            exif_block(latitude=(dms(36.8065), "N"), longitude=(dms(10.1815), "E")),
        )
    )
    processed = process_photo(original)
    assert processed.capture is not None
    assert processed.capture.has_location

    stored = await photos.keep(facts(), processed)

    saved = await disk.get(stored.key)
    image = Image.open(io.BytesIO(saved))
    assert image.getexif().get_ifd(ExifTags.IFD.GPSInfo) == {}
    assert b"Exif" not in saved


async def test_publishing_copies_the_photo_to_its_own_public_key_and_leaves_the_private_one(
    photos, disk
):
    stored = await photos.keep(facts(), photo())

    published = await photos.publish(facts(), stored.key)

    assert published.key.startswith("public/")
    assert published.key.split("/")[1] != stored.key.split("/")[1]
    assert published.url == f"https://api.tabsira.test/media/{published.key}"
    assert await disk.get(published.key) == await disk.get(stored.key) == CLEAN


async def test_publishing_what_is_not_there_is_not_found_and_leaves_no_public_copy(photos, disk):
    with pytest.raises(ObjectNotFoundError):
        await photos.publish(facts(), new_private_key())

    assert not (disk.root / "public").exists()


async def test_only_a_private_copy_can_be_published(photos):
    with pytest.raises(InvalidKeyError):
        await photos.publish(facts(), new_public_key())
    with pytest.raises(InvalidKeyError):
        await photos.publish(facts(), "../etc/passwd")


async def test_withdrawing_deletes_the_public_copy_only_and_may_be_repeated(photos, disk):
    stored = await photos.keep(facts(), photo())
    published = await photos.publish(facts(), stored.key)

    await photos.withdraw(published.key)
    await photos.withdraw(published.key)

    assert not await disk.exists(published.key)
    assert await disk.exists(stored.key)


async def test_a_private_key_cannot_be_withdrawn_and_a_public_one_cannot_be_removed(photos):
    with pytest.raises(InvalidKeyError):
        await photos.withdraw(new_private_key())
    with pytest.raises(InvalidKeyError):
        await photos.remove(new_public_key())


async def test_removing_deletes_the_private_copy(photos, disk):
    stored = await photos.keep(facts(), photo())

    await photos.remove(stored.key)

    assert not await disk.exists(stored.key)


async def test_an_owner_sees_their_photo_through_a_short_lived_signed_link(photos, moving_clock):
    stored = await photos.keep(facts(), photo())

    link = photos.private_url(stored.key)
    shorter = photos.private_url(stored.key, ttl_seconds=60)

    assert link.startswith(f"https://api.tabsira.test/media/{stored.key}?expires=")
    assert f"expires={int(moving_clock.now.timestamp()) + 300}" in link
    assert f"expires={int(moving_clock.now.timestamp()) + 60}" in shorter


def test_no_signed_link_is_made_for_a_published_copy_or_for_what_is_not_a_key(photos):
    with pytest.raises(InvalidKeyError):
        photos.private_url(new_public_key())
    with pytest.raises(InvalidKeyError):
        photos.private_url("../etc/passwd")


def test_the_store_is_built_from_the_settings(make_settings):
    store = build_photo_store(make_settings())

    assert isinstance(store, PhotoStore)
    assert isinstance(store.storage, LocalStorage)
