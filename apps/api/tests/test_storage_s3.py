"""The S3 photo store, against moto's in-process S3: private objects, a public prefix, short links."""

from __future__ import annotations

import socket
import uuid
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlsplit

import boto3
import pytest
from botocore.exceptions import EndpointConnectionError
from botocore.stub import Stubber
from moto import mock_aws

from src.config import Environment
from src.storage import build_storage, s3
from src.storage.base import (
    InvalidKeyError,
    InvalidTtlError,
    ObjectNotFoundError,
    StorageConfigError,
    StorageUnavailableError,
    new_private_key,
    new_public_key,
    owner_prefix,
)
from src.storage.local import LocalStorage
from src.storage.s3 import PRIVATE_CACHE_CONTROL, PUBLIC_CACHE_CONTROL, S3Storage

BUCKET = "tabsira-photos"
PUBLIC_BASE = "https://media.tabsira.me"
JPEG = b"\xff\xd8\xff\xe0 not really a photo \xff\xd9"
S3_SETTINGS = {
    "storage_backend": "s3",
    "s3_bucket": BUCKET,
    "s3_access_key_id": "AKIAEXAMPLE",
    "s3_secret_access_key": "s3-secret-value",
    "s3_public_base_url": PUBLIC_BASE,
}


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """A test of the store must never open a connection: moto answers in this process."""

    def refuse(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("a test tried to open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.fixture
def bucket(make_settings) -> Iterator[S3Storage]:
    """A store over a fresh fake bucket."""
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield S3Storage.from_settings(make_settings(**S3_SETTINGS))


def raw(store: S3Storage) -> Any:
    """The same fake bucket, read with a client of the test's own."""
    return boto3.client("s3", region_name="us-east-1")


# ─── Objects ──────────────────────────────────────────────────────────────────


async def test_an_object_is_stored_under_its_key_and_read_back_byte_for_byte(bucket):
    key = new_private_key()

    await bucket.put(key, JPEG)

    assert await bucket.get(key) == JPEG
    assert await bucket.exists(key)
    listed = raw(bucket).list_objects_v2(Bucket=BUCKET)["Contents"]
    assert [item["Key"] for item in listed] == [key]


async def test_a_private_object_is_marked_uncacheable_and_a_public_one_cacheable(bucket):
    private, public = new_private_key(), new_public_key()

    await bucket.put(private, JPEG)
    await bucket.put(public, JPEG)

    client = raw(bucket)
    first = client.head_object(Bucket=BUCKET, Key=private)
    second = client.head_object(Bucket=BUCKET, Key=public)
    assert (first["ContentType"], first["CacheControl"]) == ("image/jpeg", PRIVATE_CACHE_CONTROL)
    assert (second["ContentType"], second["CacheControl"]) == ("image/jpeg", PUBLIC_CACHE_CONTROL)


async def test_the_store_never_sets_an_object_public(bucket):
    key = new_public_key()

    await bucket.put(key, JPEG)

    grants = raw(bucket).get_object_acl(Bucket=BUCKET, Key=key)["Grants"]
    assert [grant["Grantee"].get("URI") for grant in grants] == [None]


async def test_a_missing_object_is_not_found_and_does_not_exist(bucket):
    key = new_private_key()

    assert not await bucket.exists(key)
    with pytest.raises(ObjectNotFoundError):
        await bucket.get(key)


async def test_deleting_removes_the_object_and_deleting_again_is_fine(bucket):
    key = new_private_key()
    await bucket.put(key, JPEG)

    await bucket.delete(key)
    await bucket.delete(key)

    assert not await bucket.exists(key)


async def test_a_copy_gets_its_own_headers_and_leaves_the_original_alone(bucket):
    private, public = new_private_key(), new_public_key()
    await bucket.put(private, JPEG)

    await bucket.copy(private, public)

    client = raw(bucket)
    assert await bucket.get(public) == JPEG
    assert client.head_object(Bucket=BUCKET, Key=public)["CacheControl"] == PUBLIC_CACHE_CONTROL
    assert client.head_object(Bucket=BUCKET, Key=private)["CacheControl"] == PRIVATE_CACHE_CONTROL
    await bucket.delete(public)
    assert await bucket.exists(private)


async def test_copying_what_is_not_there_is_not_found(bucket):
    with pytest.raises(ObjectNotFoundError):
        await bucket.copy(new_private_key(), new_public_key())


async def test_a_key_that_is_not_one_never_reaches_the_bucket(bucket):
    with Stubber(bucket.client):  # any call the stubber was not told to expect fails
        for call in (
            bucket.put("../x.jpg", JPEG),
            bucket.get("../x.jpg"),
            bucket.exists("../x.jpg"),
            bucket.delete("../x.jpg"),
            bucket.copy("../x.jpg", new_public_key()),
            bucket.copy(new_private_key(), "../x.jpg"),
        ):
            with pytest.raises(InvalidKeyError):
                await call
        with pytest.raises(InvalidKeyError):
            await bucket.put(new_private_key(), b"")
        with pytest.raises(InvalidKeyError):
            await bucket.put(new_private_key(), JPEG, content_type="text/html")


# ─── Failures ─────────────────────────────────────────────────────────────────


async def test_a_refusal_by_the_service_is_storage_unavailable_and_logs_no_key(bucket, caplog):
    key = new_private_key()
    with Stubber(bucket.client) as stub:
        stub.add_client_error("put_object", "AccessDenied", http_status_code=403)
        with (
            caplog.at_level("WARNING", logger="tabsira.storage"),
            pytest.raises(StorageUnavailableError),
        ):
            await bucket.put(key, JPEG)

    assert "AccessDenied" in caplog.text
    assert key not in caplog.text
    assert BUCKET not in caplog.text


async def test_a_service_that_cannot_be_reached_is_storage_unavailable(bucket, monkeypatch, caplog):
    def unreachable(**_arguments: Any) -> None:
        raise EndpointConnectionError(endpoint_url="https://secret-host.example")

    monkeypatch.setattr(bucket.client, "head_object", unreachable)

    with (
        caplog.at_level("WARNING", logger="tabsira.storage"),
        pytest.raises(StorageUnavailableError),
    ):
        await bucket.exists(new_private_key())

    assert "EndpointConnectionError" in caplog.text
    assert "secret-host" not in caplog.text


async def test_a_404_without_a_code_is_still_not_found(bucket):
    with Stubber(bucket.client) as stub:
        stub.add_client_error("get_object", "Whatever", http_status_code=404)
        with pytest.raises(ObjectNotFoundError):
            await bucket.get(new_private_key())


# ─── Addresses ────────────────────────────────────────────────────────────────


def query_of(url: str) -> dict[str, str]:
    return {name: values[0] for name, values in parse_qs(urlsplit(url).query).items()}


def test_a_signed_link_is_a_get_that_expires_in_five_minutes_by_default(bucket):
    key = new_private_key()

    url = bucket.signed_url(key)

    split = urlsplit(url)
    assert split.scheme == "https"
    assert split.path.endswith(f"/{key}")
    assert BUCKET in split.netloc + split.path
    query = query_of(url)
    assert query["X-Amz-Expires"] == "300"
    assert query["X-Amz-Algorithm"] == "AWS4-HMAC-SHA256"
    assert len(query["X-Amz-Signature"]) == 64
    assert "X-Amz-Security-Token" not in query


def test_a_link_may_ask_for_a_shorter_life_and_never_a_longer_one_than_an_hour(bucket):
    assert query_of(bucket.signed_url(new_private_key(), ttl_seconds=60))["X-Amz-Expires"] == "60"
    assert (
        query_of(bucket.signed_url(new_private_key(), ttl_seconds=3600))["X-Amz-Expires"] == "3600"
    )
    for bad in (0, -1, 3601):
        with pytest.raises(InvalidTtlError):
            bucket.signed_url(new_private_key(), ttl_seconds=bad)


def test_no_link_is_made_for_what_is_not_a_key(bucket):
    with pytest.raises(InvalidKeyError):
        bucket.signed_url("../etc/passwd")


def test_the_signature_depends_on_the_secret_and_the_key(bucket, make_settings):
    key = new_private_key()
    other = S3Storage.from_settings(
        make_settings(**{**S3_SETTINGS, "s3_secret_access_key": "another-secret"})
    )

    assert (
        query_of(bucket.signed_url(key))["X-Amz-Signature"]
        != query_of(other.signed_url(key))["X-Amz-Signature"]
    )
    assert (
        query_of(bucket.signed_url(key))["X-Amz-Signature"]
        != query_of(bucket.signed_url(new_private_key()))["X-Amz-Signature"]
    )


def test_only_a_published_copy_has_a_public_address_under_the_public_base(bucket):
    public = new_public_key()

    assert bucket.public_url(public) == f"{PUBLIC_BASE}/{public}"
    with pytest.raises(InvalidKeyError):
        bucket.public_url(new_private_key())
    with pytest.raises(InvalidKeyError):
        bucket.public_url("../etc/passwd")


def test_another_provider_is_addressed_by_path_at_its_own_endpoint(make_settings):
    store = S3Storage.from_settings(
        make_settings(
            **{
                **S3_SETTINGS,
                "s3_endpoint_url": "https://s3.gra.example.test",
                "s3_region": "gra",
            }
        )
    )
    key = new_private_key()

    url = store.signed_url(key)

    split = urlsplit(url)
    assert split.netloc == "s3.gra.example.test"
    assert split.path == f"/{BUCKET}/{key}"
    assert "gra" in query_of(url)["X-Amz-Credential"]
    assert store.client.meta.endpoint_url == "https://s3.gra.example.test"


def test_the_client_is_signed_with_v4_and_has_short_timeouts_and_retries(bucket):
    config = bucket.client.meta.config

    assert config.signature_version == "s3v4"
    assert (config.connect_timeout, config.read_timeout) == (3, 10)
    assert config.retries["mode"] == "standard"
    # Three retries after the first attempt.
    assert config.retries["total_max_attempts"] == 4


# ─── The factory ──────────────────────────────────────────────────────────────


def test_the_settings_choose_the_store(make_settings):
    local = build_storage(make_settings())
    s3 = build_storage(make_settings(**S3_SETTINGS))

    assert isinstance(local, LocalStorage)
    assert isinstance(s3, S3Storage)
    assert s3.bucket == BUCKET
    assert s3.default_ttl_seconds == 300
    assert s3.public_base_url == PUBLIC_BASE
    assert local.default_ttl_seconds == 300
    assert local.base_url == "https://api.tabsira.test"


PRODUCTION = {
    "environment": "production",
    "site_url": "https://tabsira.me",
    "api_url": "https://api.tabsira.me",
    "admin_url": "https://admin.tabsira.me",
    "cors_origins": "https://tabsira.me",
    "session_cookie_domain": ".tabsira.me",
    "hash_secret": "not-a-real-secret-but-long-enough-for-the-rule",
    "ai_ovh": {"api_key": "ovh-key-123"},
    "ai_openai": {"api_key": "openai-key-123"},
    "disabled_features": "admin",
    "redis_password": "redis-secret",
}


def test_production_refuses_the_local_store(make_settings):
    development = make_settings()
    production = development.model_copy(update={"environment": Environment.PRODUCTION})

    with pytest.raises(StorageConfigError, match="production keeps photos in S3"):
        build_storage(production)


def test_production_with_a_bucket_uses_s3(make_settings):
    assert isinstance(build_storage(make_settings(**PRODUCTION, **S3_SETTINGS)), S3Storage)


def test_an_explicit_local_store_wins_over_a_bucket(make_settings, tmp_path):
    values = {**S3_SETTINGS, "storage_backend": "local", "local_media_dir": str(tmp_path)}

    assert isinstance(build_storage(make_settings(**values)), LocalStorage)


def test_a_public_object_is_cached_for_five_minutes_and_never_immutable():
    assert PUBLIC_CACHE_CONTROL == "public, max-age=300"


# ─── One folder per account ────────────────────────────────────────────────────

ACCOUNT = uuid.UUID("0199b6a0-0000-7000-8000-0000000000aa")


async def test_deleting_an_account_folder_removes_its_objects_only_page_by_page(
    bucket, monkeypatch
):
    monkeypatch.setattr(s3, "DELETE_BATCH", 2)
    mine = [new_private_key(ACCOUNT) for _ in range(5)]
    theirs = new_private_key(uuid.UUID("0199b6a0-0000-7000-8000-0000000000bb"))
    for key in [*mine, theirs]:
        await bucket.put(key, JPEG)

    assert await bucket.delete_prefix(owner_prefix(ACCOUNT)) == 5
    listed = raw(bucket).list_objects_v2(Bucket=BUCKET)["Contents"]
    assert [item["Key"] for item in listed] == [theirs]
    assert await bucket.delete_prefix(owner_prefix(ACCOUNT)) == 0


async def test_a_folder_the_service_cannot_fully_delete_is_storage_unavailable(bucket, monkeypatch):
    await bucket.put(new_private_key(ACCOUNT), JPEG)

    def refuse(**_arguments):
        return {"Errors": [{"Code": "AccessDenied"}]}

    monkeypatch.setattr(bucket.client, "delete_objects", refuse)
    with pytest.raises(StorageUnavailableError):
        await bucket.delete_prefix(owner_prefix(ACCOUNT))


async def test_only_an_account_folder_can_be_deleted_whole(bucket):
    for prefix in ("private/", "public/", "private/users/"):
        with pytest.raises(InvalidKeyError):
            await bucket.delete_prefix(prefix)


async def test_a_listing_that_says_there_is_more_but_not_where_is_storage_unavailable(
    bucket, monkeypatch
):
    def endless(**_arguments):
        return {"Contents": [], "IsTruncated": True}

    monkeypatch.setattr(bucket.client, "list_objects_v2", endless)
    with pytest.raises(StorageUnavailableError):
        await bucket.delete_prefix(owner_prefix(ACCOUNT))
