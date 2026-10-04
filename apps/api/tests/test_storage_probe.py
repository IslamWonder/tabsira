"""Production refuses to start when the photo storage cannot be used (decision 44)."""

from __future__ import annotations

import logging
import os
import socket
import stat
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from botocore.exceptions import (
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)
from botocore.stub import Stubber
from moto import mock_aws
from pydantic import ValidationError

from src import main
from src.cli import check_config
from src.config import Environment, Settings
from src.storage import probe, s3
from src.storage.probe import StorageProbeError, check_storage, probe_storage

BUCKET = "tabsira-photos"
ENDPOINT = "https://s3.gra.example.net"
ACCESS_KEY = "AKIAEXAMPLEKEYID"
SECRET_KEY = "s3-secret-value-never-printed"
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
    "feature_admin": False,
    "redis_password": "redis-secret",
}
S3_SETTINGS = {
    "s3_endpoint_url": ENDPOINT,
    "s3_bucket": BUCKET,
    "s3_access_key_id": ACCESS_KEY,
    "s3_secret_access_key": SECRET_KEY,
    "s3_public_base_url": "https://media.tabsira.me",
}


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("a test tried to open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.fixture
def client() -> Iterator[Any]:
    """A client of a fresh fake bucket; the probe is given this one."""
    with mock_aws():
        fake = boto3.client("s3", region_name="us-east-1")
        fake.create_bucket(Bucket=BUCKET)
        yield fake


@pytest.fixture
def uses_client(client: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    seen: dict[str, Any] = {}

    def build(_settings: Any, **options: Any) -> Any:
        seen.update(options)
        return client

    monkeypatch.setattr(s3, "build_client", build)
    client.options = seen
    return client


def production(**more: Any) -> dict[str, Any]:
    return {**PRODUCTION, **S3_SETTINGS, **more}


# ─── S3 ───────────────────────────────────────────────────────────────────────


def test_a_good_bucket_passes_and_leaves_no_probe_object_behind(uses_client, make_settings):
    probe_storage(make_settings(**production()))

    assert "Contents" not in uses_client.list_objects_v2(Bucket=BUCKET)
    assert uses_client.options == {"connect_timeout": 5, "read_timeout": 5, "attempts": 1}


def test_the_probe_object_is_private_with_a_random_name(uses_client, make_settings, monkeypatch):
    keys: list[str] = []
    original = uses_client.put_object

    def spy(**arguments: Any) -> Any:
        keys.append(arguments["Key"])
        return original(**arguments)

    monkeypatch.setattr(uses_client, "put_object", spy)
    probe_storage(make_settings(**production()))
    probe_storage(make_settings(**production()))

    assert len(set(keys)) == 2
    assert all(k.startswith("private/") for k in keys)


def test_a_missing_bucket_fails_and_names_the_bucket_and_endpoint(uses_client, make_settings):
    uses_client.delete_bucket(Bucket=BUCKET)

    with pytest.raises(StorageProbeError) as caught:
        probe_storage(make_settings(**production()))

    message = str(caught.value)
    assert BUCKET in message
    assert "s3.gra.example.net" in message
    assert "HeadBucket" in message


def test_wrong_keys_fail_without_printing_them(uses_client, make_settings):
    with Stubber(uses_client) as stub:
        stub.add_client_error("head_bucket", "InvalidAccessKeyId", http_status_code=403)
        with pytest.raises(StorageProbeError) as caught:
            probe_storage(make_settings(**production()))

    message = str(caught.value)
    assert "InvalidAccessKeyId" in message
    assert BUCKET in message
    assert ACCESS_KEY not in message
    assert SECRET_KEY not in message


def test_a_key_that_may_read_but_not_write_fails_at_the_put(uses_client, make_settings):
    with Stubber(uses_client) as stub:
        stub.add_response("head_bucket", {})
        stub.add_client_error("put_object", "AccessDenied", http_status_code=403)
        with pytest.raises(StorageProbeError, match=r"PutObject.*AccessDenied"):
            probe_storage(make_settings(**production()))


def test_a_key_that_may_not_delete_fails_at_the_delete(uses_client, make_settings):
    with Stubber(uses_client) as stub:
        stub.add_response("head_bucket", {})
        stub.add_response("put_object", {})
        stub.add_client_error("delete_object", "AccessDenied", http_status_code=403)
        with pytest.raises(StorageProbeError, match="DeleteObject"):
            probe_storage(make_settings(**production()))


@pytest.mark.parametrize(
    "error",
    [
        EndpointConnectionError(endpoint_url="https://user:hunter2@secret-host.example"),
        ConnectTimeoutError(endpoint_url="https://secret-host.example"),
    ],
)
def test_an_unreachable_endpoint_fails_and_names_only_the_configured_host(
    uses_client, make_settings, monkeypatch, error
):
    def unreachable(**_arguments: Any) -> None:
        raise error

    monkeypatch.setattr(uses_client, "head_bucket", unreachable)

    with pytest.raises(StorageProbeError) as caught:
        probe_storage(make_settings(**production()))

    message = str(caught.value)
    assert type(error).__name__ in message
    assert "s3.gra.example.net" in message
    assert "hunter2" not in message
    assert "secret-host" not in message


def test_a_bucket_on_aws_names_aws_as_the_endpoint(uses_client, make_settings):
    uses_client.delete_bucket(Bucket=BUCKET)

    with pytest.raises(StorageProbeError, match="AWS"):
        probe_storage(make_settings(**production(s3_endpoint_url="")))


def test_the_endpoint_is_named_with_its_port(uses_client, make_settings):
    uses_client.delete_bucket(Bucket=BUCKET)

    with pytest.raises(StorageProbeError, match=r"minio\.example\.net:9000"):
        probe_storage(make_settings(**production(s3_endpoint_url="http://minio.example.net:9000")))


def test_the_real_client_has_short_timeouts_and_no_retry(make_settings):
    client = s3.build_client(
        make_settings(**production()), connect_timeout=5, read_timeout=5, attempts=1
    )

    assert (client.meta.config.connect_timeout, client.meta.config.read_timeout) == (5, 5)
    assert client.meta.config.retries["total_max_attempts"] == 1


# ─── Local disk (development and test only) ───────────────────────────────────


def test_production_refuses_a_probe_of_the_local_disk(make_settings):
    development = make_settings()
    production_settings = development.model_copy(update={"environment": Environment.PRODUCTION})

    with pytest.raises(StorageProbeError, match="production keeps photos in S3"):
        probe_storage(production_settings)


def test_a_writable_folder_passes_and_keeps_nothing(make_settings, tmp_path):
    folder = tmp_path / "media"
    folder.mkdir()

    probe_storage(make_settings(local_media_dir=str(folder)))

    assert list(folder.iterdir()) == []


def test_a_missing_folder_is_made_in_development(make_settings, tmp_path):
    folder = tmp_path / "data" / "media"

    probe_storage(make_settings(local_media_dir=str(folder)))

    assert folder.is_dir()
    assert list(folder.iterdir()) == []


def test_a_folder_the_process_cannot_write_fails(make_settings, tmp_path, monkeypatch):
    def refused(*_args: Any, **_kwargs: Any) -> int:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(probe.os, "open", refused)

    with pytest.raises(StorageProbeError, match="cannot write"):
        probe_storage(make_settings(local_media_dir=str(tmp_path)))


# ─── At startup ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("failure", ["missing bucket", "wrong keys", "unreachable"])
async def test_production_stops_at_startup_when_the_bucket_cannot_be_used(
    uses_client, make_settings, monkeypatch, failure
):
    if failure == "missing bucket":
        uses_client.delete_bucket(Bucket=BUCKET)
    elif failure == "unreachable":

        def unreachable(**_arguments: Any) -> None:
            raise EndpointConnectionError(endpoint_url="https://secret-host.example")

        monkeypatch.setattr(uses_client, "head_bucket", unreachable)
    with Stubber(uses_client) as stub:
        if failure == "wrong keys":
            stub.add_client_error("head_bucket", "InvalidAccessKeyId", http_status_code=403)
        with pytest.raises(StorageProbeError) as caught:
            await check_storage(make_settings(**production()))

    assert BUCKET in str(caught.value)
    assert SECRET_KEY not in str(caught.value)


async def test_production_starts_when_the_bucket_works(uses_client, make_settings, caplog):
    with caplog.at_level(logging.INFO, logger="tabsira.storage"):
        await check_storage(make_settings(**production()))

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


async def test_development_only_warns_when_the_bucket_cannot_be_used(
    uses_client, make_settings, caplog
):
    uses_client.delete_bucket(Bucket=BUCKET)

    with caplog.at_level(logging.WARNING, logger="tabsira.storage"):
        await check_storage(make_settings(**{**S3_SETTINGS, "environment": "development"}))

    assert [r.levelno for r in caplog.records] == [logging.WARNING]
    assert BUCKET in caplog.text
    assert SECRET_KEY not in caplog.text


async def test_the_test_environment_only_warns_too(make_settings, tmp_path, caplog, monkeypatch):
    def broken(_settings: Any) -> None:
        raise StorageProbeError("the storage is down")

    monkeypatch.setattr(probe, "probe_storage", broken)

    with caplog.at_level(logging.WARNING, logger="tabsira.storage"):
        await check_storage(make_settings(local_media_dir=str(tmp_path)))

    assert "the storage is down" in caplog.text


async def test_the_lifespan_stops_a_production_boot_with_a_bad_bucket(uses_client, make_settings):
    uses_client.delete_bucket(Bucket=BUCKET)
    application = main.create_app(make_settings(**production()))

    with pytest.raises(StorageProbeError):
        async with application.router.lifespan_context(application):
            raise AssertionError("the application must not start")


# ─── check_config ─────────────────────────────────────────────────────────────


def test_check_config_reports_ok_when_the_bucket_works(uses_client, make_settings):
    assert check_config.storage_report(make_settings(**production())) == ("storage: ok", True)


def test_check_config_reports_the_failure_and_fails_in_production(uses_client, make_settings):
    uses_client.delete_bucket(Bucket=BUCKET)

    line, ok = check_config.storage_report(make_settings(**production()))

    assert not ok
    assert line.startswith("storage: FAILED, ")
    assert BUCKET in line


def test_check_config_does_not_fail_a_development_machine(make_settings, monkeypatch, tmp_path):
    def broken(_settings: Any) -> None:
        raise StorageProbeError("the storage is down")

    monkeypatch.setattr(check_config, "probe_storage", broken)
    line, ok = check_config.storage_report(make_settings(local_media_dir=str(tmp_path)))

    assert ok
    assert line == "storage: FAILED, the storage is down"


def test_main_exits_1_when_the_production_bucket_fails(
    uses_client, make_settings, monkeypatch, capsys
):
    uses_client.delete_bucket(Bucket=BUCKET)
    settings = make_settings(**production())
    monkeypatch.setattr(check_config, "load_settings", lambda: settings)

    assert check_config.main([]) == 1
    assert "storage: FAILED" in capsys.readouterr().err


def test_main_exits_0_when_the_bucket_works(uses_client, make_settings, monkeypatch, capsys):
    settings = make_settings(**production())
    monkeypatch.setattr(check_config, "load_settings", lambda: settings)

    assert check_config.main([]) == 0
    assert "storage: ok" in capsys.readouterr().out


# ─── Review fixes ─────────────────────────────────────────────────────────────


def test_a_client_that_cannot_be_built_fails_cleanly_without_echoing_the_url(
    make_settings, monkeypatch
):
    def invalid(_settings: Any, **_options: Any) -> Any:
        raise ValueError("Invalid endpoint: https://user:hunter2@bad_host.example")

    monkeypatch.setattr(s3, "build_client", invalid)

    with pytest.raises(StorageProbeError) as caught:
        probe_storage(make_settings(**production()))

    assert "client failed (ValueError)" in str(caught.value)
    assert "hunter2" not in str(caught.value)
    assert BUCKET in str(caught.value)


def test_a_bad_region_fails_cleanly(make_settings):
    with pytest.raises(StorageProbeError, match=r"client failed \(InvalidRegionError\)"):
        probe_storage(make_settings(**production(s3_region="not a region!")))


async def test_a_client_that_cannot_be_built_only_warns_in_development(
    make_settings, monkeypatch, caplog
):
    def invalid(_settings: Any, **_options: Any) -> Any:
        raise ValueError("Invalid endpoint")

    monkeypatch.setattr(s3, "build_client", invalid)

    with caplog.at_level(logging.WARNING, logger="tabsira.storage"):
        await check_storage(make_settings(**{**S3_SETTINGS, "environment": "development"}))

    assert "client failed" in caplog.text


@pytest.mark.parametrize("key", ["s3_endpoint_url", "s3_public_base_url"])
@pytest.mark.parametrize("value", ["https://user:pw@s3.example.net", "https://user@s3.example.net"])
def test_an_s3_address_with_a_user_name_or_password_is_refused(key, value):
    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None, **{key: value})

    assert key in str(caught.value)
    assert "no user name or password" in str(caught.value)


def test_a_probe_object_is_deleted_even_when_the_put_failed_after_storing_it(
    uses_client, make_settings, monkeypatch
):
    deleted: list[str] = []
    real_put = uses_client.put_object
    real_delete = uses_client.delete_object

    def timed_out(**arguments: Any) -> None:
        real_put(**arguments)
        raise ReadTimeoutError(endpoint_url="https://secret-host.example")

    def spy(**arguments: Any) -> Any:
        deleted.append(arguments["Key"])
        return real_delete(**arguments)

    monkeypatch.setattr(uses_client, "put_object", timed_out)
    monkeypatch.setattr(uses_client, "delete_object", spy)

    with pytest.raises(StorageProbeError, match=r"PutObject failed \(ReadTimeoutError\)"):
        probe_storage(make_settings(**production()))

    assert len(deleted) == 1
    assert "Contents" not in uses_client.list_objects_v2(Bucket=BUCKET)


def test_a_failed_cleanup_after_a_failed_put_does_not_replace_the_puts_error(
    uses_client, make_settings, monkeypatch
):
    def put_fails(**_arguments: Any) -> None:
        raise ReadTimeoutError(endpoint_url="https://secret-host.example")

    def delete_fails(**_arguments: Any) -> None:
        raise EndpointConnectionError(endpoint_url="https://secret-host.example")

    monkeypatch.setattr(uses_client, "put_object", put_fails)
    monkeypatch.setattr(uses_client, "delete_object", delete_fails)

    with pytest.raises(StorageProbeError, match=r"PutObject failed \(ReadTimeoutError\)"):
        probe_storage(make_settings(**production()))


def test_the_local_probe_makes_every_missing_folder_private(make_settings, tmp_path):
    old = os.umask(0)
    try:
        probe_storage(make_settings(local_media_dir=str(tmp_path / "a" / "b" / "media")))
    finally:
        os.umask(old)

    modes = [stat.S_IMODE(p.stat().st_mode) for p in (tmp_path / "a", tmp_path / "a" / "b")]
    assert modes == [0o700, 0o700]
