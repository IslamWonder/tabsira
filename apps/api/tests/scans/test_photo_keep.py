"""«تمّ» keeps the scan's photo for a consenting account, and for nobody else (v2 §19)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest
from fakeredis import FakeAsyncRedis
from redis.exceptions import RedisError
from sqlalchemy import select

from src.models import Insight, Profile
from src.models.profile import AgeRange
from src.owner import Owner
from src.pipeline.schemas import EncodedImage
from src.scans import buffer
from src.services import photo_service
from src.storage.base import StorageUnavailableError
from src.storage.local import LocalStorage
from src.storage.photos import PhotoStore
from tests.scans.builders import insight_row, scan_row
from tests.scans.conftest import as_guest, make_account, photo, sign_in


@pytest.fixture
def media(tmp_path: Path) -> Path:
    return tmp_path / "media"


@pytest.fixture
def photos(media: Path, flow_settings, flow_app) -> PhotoStore:
    """A photo store on the test's own directory, set on the application."""
    store = PhotoStore(
        LocalStorage(
            media,
            base_url="https://api.tabsira.test",
            signing_key=b"k" * 32,
            default_ttl_seconds=300,
        ),
        flow_settings,
    )
    flow_app.state.photo_store = store
    return store


def objects(media: Path) -> list[str]:
    """Every object kept, as its key, in a stable order (an older private copy is sharded on disk)."""
    keys = []
    for path in media.rglob("*.jpg"):
        parts = path.relative_to(media).parts
        keys.append("/".join(parts) if parts[1] == "users" else f"{parts[0]}/{path.name}")
    return sorted(keys)


async def scanned_insight(
    store, redis: FakeAsyncRedis, settings, owner: Owner, *, sensitive: bool = False, **values: Any
) -> int:
    """A finished scan whose stripped photo is still in the temporary store, and its insight."""
    async with store() as db:
        scan = scan_row(owner, status="done", sensitive=sensitive)
        db.add(scan)
        await db.flush()
        insight = insight_row(owner, scan_id=scan.id, **values)
        db.add(insight)
        await db.flush()
        await db.commit()
        image = EncodedImage(data=photo(), width=96, height=64)
        await buffer.put(
            redis, scan.id, full=image, model=image, ttl=3600, key=buffer.photo_key(settings)
        )
        return insight.id


async def consenting_account(
    browser,
    store,
    *,
    age_range: AgeRange = AgeRange.FROM_25_TO_39,
    consent: bool = True,
    email: str = "reader@example.com",
) -> Owner:
    user = await make_account(store, email)
    async with store() as db:
        profile = (await db.scalars(select(Profile).where(Profile.user_id == user.id))).one()
        profile.photo_storage_consent = consent
        profile.age_range = age_range
        await db.commit()
    await sign_in(browser, email)
    return Owner(user_id=user.id)


async def complete(browser, insight_id: int) -> dict[str, Any]:
    response = await browser.post(f"/insights/{insight_id}/complete")
    assert response.status_code == 200, response.text
    return response.json()


async def photo_key_of(store, insight_id: int) -> str | None:
    async with store() as db:
        return await db.scalar(select(Insight.photo_key).where(Insight.id == insight_id))


async def test_the_first_tamm_of_a_consenting_account_keeps_one_private_copy(
    browser, store, flow_settings, redis, photos, media
):
    owner = await consenting_account(browser, store)
    insight_id = await scanned_insight(store, redis, flow_settings, owner)

    first = await complete(browser, insight_id)
    second = await complete(browser, insight_id)

    key = await photo_key_of(store, insight_id)
    assert (first["first_time"], second["first_time"]) == (True, False)
    assert key is not None and key.startswith("private/")
    assert objects(media) == [key]
    # The kept copy is a plain JPEG the store will sign for its owner, and the buffer copy lives on.
    assert (await photos.storage.get(key))[:2] == b"\xff\xd8"
    assert photos.private_url(key).startswith("https://api.tabsira.test/")
    async with store() as db:
        scan_id = await db.scalar(select(Insight.scan_id).where(Insight.id == insight_id))
    assert await buffer.kept(redis, scan_id, buffer.Copy.FULL)
    # The key never reaches the completion answer.
    assert key not in str(first) and key not in str(second)


async def test_nothing_is_kept_without_consent_under_13_or_for_a_sensitive_scene(
    browser, other, store, flow_settings, redis, photos, media
):
    refused = await consenting_account(browser, store, consent=False)
    no_consent = await scanned_insight(store, redis, flow_settings, refused)
    await complete(browser, no_consent)

    young = await consenting_account(
        other, store, age_range=AgeRange.UNDER_13, email="young@example.com"
    )
    under_13 = await scanned_insight(store, redis, flow_settings, young)
    await complete(other, under_13)

    async with store() as db:
        profile = (await db.scalars(select(Profile).where(Profile.user_id == young.user_id))).one()
        profile.age_range = AgeRange.FROM_25_TO_39
        await db.commit()
    sensitive = await scanned_insight(store, redis, flow_settings, young, sensitive=True)
    await complete(other, sensitive)

    assert objects(media) == []
    for insight_id in (no_consent, under_13, sensitive):
        assert await photo_key_of(store, insight_id) is None


async def test_a_guest_s_photo_is_never_kept(browser, store, flow_settings, redis, photos, media):
    guest = await as_guest(browser, store, flow_settings)
    insight_id = await scanned_insight(store, redis, flow_settings, guest)

    await complete(browser, insight_id)

    assert objects(media) == []
    assert await photo_key_of(store, insight_id) is None


async def test_nothing_is_kept_while_the_feature_is_off(
    browser, store, flow_settings, redis, photos, media, flow_app
):
    flow_app.state.settings = flow_settings.model_copy(update={"feature_photo_storage": False})
    flow_app.state.photo_store = PhotoStore(photos.storage, flow_app.state.settings)
    owner = await consenting_account(browser, store)
    insight_id = await scanned_insight(store, redis, flow_settings, owner)

    await complete(browser, insight_id)

    assert objects(media) == []
    assert await photo_key_of(store, insight_id) is None


async def test_an_expired_buffer_or_a_tutorial_insight_keeps_nothing(
    browser, store, flow_settings, redis, photos, media
):
    owner = await consenting_account(browser, store)
    expired = await scanned_insight(store, redis, flow_settings, owner)
    async with store() as db:
        scan_id = await db.scalar(select(Insight.scan_id).where(Insight.id == expired))
        tutorial = insight_row(
            owner,
            origin="tutorial",
            tutorial_scene="rain",
            tutorial_slug="rain-1",
            engine="prepared",
        )
        db.add(tutorial)
        await db.commit()
        tutorial_id = tutorial.id
    await buffer.drop(redis, scan_id)

    await complete(browser, expired)
    await complete(browser, tutorial_id)

    assert objects(media) == []
    assert await photo_key_of(store, expired) is None
    assert await photo_key_of(store, tutorial_id) is None


class BrokenStorage:
    """A storage that cannot be reached."""

    async def put(self, key: str, data: bytes, *, content_type: str = "image/jpeg") -> None:
        raise StorageUnavailableError("down")


async def test_tamm_still_succeeds_when_redis_or_the_store_fails(
    browser, store, flow_settings, redis, photos, media, flow_app, monkeypatch, caplog
):
    owner = await consenting_account(browser, store)
    store_down = await scanned_insight(store, redis, flow_settings, owner)
    redis_down = await scanned_insight(store, redis, flow_settings, owner)
    not_an_image = await scanned_insight(store, redis, flow_settings, owner)
    async with store() as db:
        scan_id = await db.scalar(select(Insight.scan_id).where(Insight.id == not_an_image))
    broken = EncodedImage(data=b"not a jpeg", width=1, height=1)
    await buffer.put(
        redis, scan_id, full=broken, model=broken, ttl=60, key=buffer.photo_key(flow_settings)
    )

    flow_app.state.photo_store = PhotoStore(BrokenStorage(), flow_settings)  # type: ignore[arg-type]
    with caplog.at_level(logging.WARNING, logger="tabsira.photos"):
        assert (await complete(browser, store_down))["first_time"] is True
        flow_app.state.photo_store = photos

        async def down(*args: Any, **kwargs: Any) -> bytes | None:
            raise RedisError("down")

        monkeypatch.setattr(buffer, "get", down)
        assert (await complete(browser, redis_down))["first_time"] is True
        monkeypatch.undo()
        assert (await complete(browser, not_an_image))["first_time"] is True

    assert objects(media) == []
    for insight_id in (store_down, redis_down, not_an_image):
        assert await photo_key_of(store, insight_id) is None
    messages = [record.getMessage() for record in caplog.records]
    assert len(messages) == 3
    # The warning names the insight, never a key, a reason about the person or the owner.
    assert all(str(owner.user_id) not in message for message in messages)


async def test_remove_deletes_both_copies_and_forgets_their_keys(photos, media, db_session):
    from src.services.image_service import ProcessedPhoto
    from src.storage.photos import PhotoFacts

    facts = PhotoFacts(
        owner_id=Owner(user_id=None).user_id,
        age_range=AgeRange.FROM_25_TO_39,
        sensitive_scene=False,
        photo_storage_consent=True,
    )
    insight = insight_row(Owner(guest_key="g" * 64))
    # The rules are not the subject here: the store is given both copies directly.
    private = "private/" + "a" * 32 + ".jpg"
    public = "public/" + "b" * 32 + ".jpg"
    await photos.storage.put(private, photo())
    await photos.storage.put(public, photo())
    insight.photo_key, insight.photo_public_key = private, public
    assert facts.refusal(photos.settings) is not None

    await photo_service.remove(photos, insight)
    await photo_service.remove(photos, insight)

    assert objects(media) == []
    assert (insight.photo_key, insight.photo_public_key) == (None, None)
    assert isinstance(ProcessedPhoto, type)
