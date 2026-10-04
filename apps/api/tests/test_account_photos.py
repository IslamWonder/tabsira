"""The photos an account kept go with the account, and the export says which exist (v2 §15, §19)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from src.models import Insight, User
from src.owner import Owner
from src.storage.base import StorageUnavailableError, new_private_key, new_public_key
from src.storage.local import LocalStorage
from src.storage.photos import PhotoStore
from tests.conftest import PASSPHRASE
from tests.scans.builders import insight_row, scan_row
from tests.support_images import jpeg_of, pixels

LOGIN = {"email": "reader@example.com", "password": PASSPHRASE}


@pytest.fixture
def media(tmp_path: Path) -> Path:
    return tmp_path / "media"


@pytest.fixture
def photos(media: Path, account_app, account_settings) -> PhotoStore:
    store = PhotoStore(
        LocalStorage(
            media,
            base_url="https://api.tabsira.test",
            signing_key=b"k" * 32,
            default_ttl_seconds=300,
        ),
        account_settings,
    )
    account_app.state.photo_store = store
    return store


@pytest.fixture
async def reader(web, make_user):
    user = await make_user(verified=True)
    await web.post("/auth/login", json=LOGIN)
    return user


def objects(media: Path) -> list[str]:
    return sorted(f"{path.parent.parent.name}/{path.name}" for path in media.rglob("*.jpg"))


async def kept(db, user: User, photos: PhotoStore, *, published: bool) -> Insight:
    """An insight of `user` with a kept photo, and a public copy when `published`."""
    owner = Owner(user_id=user.id)
    scan = scan_row(owner, status="done")
    db.add(scan)
    await db.flush()
    private = new_private_key()
    await photos.storage.put(private, jpeg_of(pixels()))
    public = None
    if published:
        public = new_public_key()
        await photos.storage.put(public, jpeg_of(pixels()))
    insight = insight_row(owner, scan_id=scan.id, photo_key=private, photo_public_key=public)
    db.add(insight)
    await db.flush()
    return insight


async def test_the_export_lists_the_kept_photos_without_their_keys(
    web, reader, db_session, photos, media
):
    shown = await kept(db_session, reader, photos, published=True)
    private_only = await kept(db_session, reader, photos, published=False)
    bare = insight_row(Owner(user_id=reader.id), scan_id=shown.scan_id)
    db_session.add(bare)
    await db_session.flush()

    response = await web.get("/account/export")

    body = response.json()
    assert response.status_code == 200
    assert body["learning"]["photos"] == [
        {"insight_id": str(shown.id), "published": True},
        {"insight_id": str(private_only.id), "published": False},
    ]
    for key in (shown.photo_key, shown.photo_public_key, private_only.photo_key):
        assert key not in response.text
    assert objects(media) == sorted(
        [shown.photo_key, shown.photo_public_key, private_only.photo_key]
    )


async def test_deleting_the_account_deletes_both_copies_of_every_photo_and_nobody_else_s(
    web, reader, db_session, photos, media, make_user
):
    mine = await kept(db_session, reader, photos, published=True)
    other = await make_user("other@example.com")
    theirs = await kept(db_session, other, photos, published=True)

    response = await web.delete("/account")

    assert response.status_code == 204
    assert await db_session.scalar(select(User).where(User.id == reader.id)) is None
    assert objects(media) == sorted([theirs.photo_key, theirs.photo_public_key])
    assert mine.photo_key not in objects(media)


async def test_a_store_that_cannot_be_reached_stops_the_deletion_and_deletes_nothing(
    web, reader, db_session, photos, media, account_app
):
    class Down(LocalStorage):
        async def delete(self, key: str) -> None:
            raise StorageUnavailableError("down")

    insight = await kept(db_session, reader, photos, published=True)
    account_app.state.photo_store = PhotoStore(
        Down(
            media,
            base_url="https://api.tabsira.test",
            signing_key=b"k" * 32,
            default_ttl_seconds=300,
        ),
        photos.settings,
    )

    response = await web.delete("/account")

    assert (response.status_code, response.json()["error"]) == (503, "STORAGE_UNAVAILABLE")
    assert await db_session.scalar(select(User).where(User.id == reader.id)) is not None
    assert objects(media) == sorted([insight.photo_key, insight.photo_public_key])
    # Still signed in: the person can ask again once the store is back.
    assert (await web.get("/auth/me")).status_code == 200
