"""The sound effect of an ontology entity: read from the bucket or the local folder, served as MP3."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import BotoCoreError, ClientError
from httpx import ASGITransport, AsyncClient

from src.config import Settings
from src.main import create_app
from src.storage.base import InvalidKeyError, ObjectNotFoundError, StorageUnavailableError
from src.storage.sounds import KEPT_SOUNDS, SoundStore, sound_key

MP3 = b"ID3-a-sound"


class FakeBody:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def read(self) -> bytes:
        return self.data


class FakeClient:
    """The one boto3 call the store makes, answering from a dict or failing as told."""

    def __init__(self, objects: dict[str, bytes], error: Exception | None = None) -> None:
        self.objects = objects
        self.error = error
        self.calls: list[str] = []

    def get_object(self, **request: str) -> dict[str, Any]:
        key = request["Key"]
        self.calls.append(key)
        if self.error is not None:
            raise self.error
        return {"Body": FakeBody(self.objects[key])}


def refusal(code: str, status: int) -> ClientError:
    return ClientError(
        {"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status}}, "GetObject"
    )


def local_file(root: Path, entity_id: str, data: bytes = MP3) -> None:
    target = root / sound_key(entity_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def test_the_key_of_a_sound_is_under_static_ontology_audio() -> None:
    assert sound_key("E001") == "static/ontology/audio/E001.mp3"
    assert sound_key("E1000") == "static/ontology/audio/E1000.mp3"


@pytest.mark.parametrize("bad", ["", "e001", "E01", "E10000", "../E001", "E001.mp3", "E00a"])
def test_a_key_is_made_only_from_an_ontology_id(bad: str) -> None:
    with pytest.raises(InvalidKeyError):
        sound_key(bad)


async def test_the_local_folder_is_read_when_there_is_no_bucket(tmp_path: Path) -> None:
    local_file(tmp_path, "E001")
    store = SoundStore(bucket="", client=None, root=tmp_path)

    assert await store.get("E001") == MP3
    with pytest.raises(ObjectNotFoundError):
        await store.get("E002")


async def test_the_bucket_is_read_with_the_key_and_the_answer_is_kept(tmp_path: Path) -> None:
    client = FakeClient({"static/ontology/audio/E003.mp3": MP3})
    store = SoundStore(bucket="b", client=client, root=tmp_path)

    assert await store.get("E003") == MP3
    assert await store.get("E003") == MP3
    assert client.calls == ["static/ontology/audio/E003.mp3"]


async def test_the_oldest_sounds_are_dropped_beyond_the_limit(tmp_path: Path) -> None:
    for number in range(1, KEPT_SOUNDS + 2):
        local_file(tmp_path, f"E{number:03d}", str(number).encode())
    store = SoundStore(bucket="", client=None, root=tmp_path)

    for number in range(1, KEPT_SOUNDS + 2):
        await store.get(f"E{number:03d}")
    await store.get("E002")  # kept: becomes the newest

    assert "static/ontology/audio/E001.mp3" not in store._kept
    assert "static/ontology/audio/E002.mp3" in store._kept
    assert len(store._kept) == KEPT_SOUNDS


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (refusal("NoSuchKey", 404), ObjectNotFoundError),
        (refusal("404", 400), ObjectNotFoundError),
        (refusal("NotFound", 200), ObjectNotFoundError),
        (refusal("AccessDenied", 403), StorageUnavailableError),
        (BotoCoreError(), StorageUnavailableError),
    ],
)
async def test_a_failing_bucket_is_told_apart_from_a_missing_sound(
    tmp_path: Path, error: Exception, expected: type[Exception]
) -> None:
    store = SoundStore(bucket="b", client=FakeClient({}, error), root=tmp_path)

    with pytest.raises(expected):
        await store.get("E004")


def test_the_store_follows_the_photo_settings(
    make_settings: Callable[..., Settings], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = SoundStore.from_settings(make_settings(local_media_dir=str(tmp_path)))
    assert local.client is None
    assert local.root == tmp_path.resolve()

    sentinel = object()
    monkeypatch.setattr("src.storage.s3.build_client", lambda settings: sentinel)
    bucket = SoundStore.from_settings(
        make_settings(
            storage_backend="s3",
            s3_bucket="tabsira",
            s3_access_key_id="key",
            s3_secret_access_key="secret",
            s3_public_base_url="https://media.tabsira.test",
        )
    )
    assert bucket.client is sentinel
    assert bucket.bucket == "tabsira"


def client_of(settings: Settings) -> AsyncClient:
    transport = ASGITransport(app=create_app(settings), client=("203.0.113.5", 4000))
    return AsyncClient(transport=transport, base_url="https://api.tabsira.test")


async def test_the_route_serves_the_mp3_and_lets_the_browser_keep_it(
    make_settings: Callable[..., Settings], tmp_path: Path
) -> None:
    local_file(tmp_path, "E010")
    async with client_of(make_settings(local_media_dir=str(tmp_path))) as http:
        response = await http.get("/sounds/ontology/E010")

    assert response.status_code == 200
    assert response.content == MP3
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.headers["cache-control"] == "public, max-age=86400"


async def test_the_route_says_404_for_a_sound_that_was_not_uploaded_and_422_for_a_bad_id(
    make_settings: Callable[..., Settings], tmp_path: Path
) -> None:
    async with client_of(make_settings(local_media_dir=str(tmp_path))) as http:
        missing = await http.get("/sounds/ontology/E011")
        bad = await http.get("/sounds/ontology/..%2F..%2Fsecret")

    assert missing.status_code == 404
    assert missing.json()["error"] == "NOT_FOUND"
    assert bad.status_code in {404, 422}


async def test_the_route_says_503_when_the_bucket_does_not_answer(
    make_settings: Callable[..., Settings], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "src.storage.s3.build_client",
        lambda settings: FakeClient({}, refusal("AccessDenied", 403)),
    )
    settings = make_settings(
        storage_backend="s3",
        s3_bucket="tabsira",
        s3_access_key_id="key",
        s3_secret_access_key="secret",
        s3_public_base_url="https://media.tabsira.test",
    )
    async with client_of(settings) as http:
        response = await http.get("/sounds/ontology/E012")

    assert response.status_code == 503
    assert response.json()["error"] == "STORAGE_UNAVAILABLE"
