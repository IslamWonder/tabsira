"""
Prove at start that the photo storage can be used (decision 44).

Production keeps photos in S3 and nowhere else. A process whose bucket is unreachable,
refused or read-only would accept a photo and lose it, so it does not start: the worker exits at boot, gunicorn's master halts, and the
pre-flight boot of `deploy/api-roll.sh` fails before any live worker is touched. In
development and test a failure is only a warning, so `make dev` works offline.

The probe writes one tiny object under a random name and removes it, which proves that the
configured keys can write and delete, not only read. A failure names the bucket and the host of the endpoint, never a key.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
from collections.abc import Callable
from contextlib import suppress
from urllib.parse import urlsplit

from botocore.exceptions import BotoCoreError, ClientError

from src.config import Environment, Settings
from src.storage.base import StorageError, new_private_key
from src.storage.local import make_private_folders

log = logging.getLogger("tabsira.storage")

# Long enough for a slow provider, short enough that a dead one fails a boot quickly.
PROBE_TIMEOUT_SECONDS = 5
_PROBE_BODY = b"tabsira storage probe"


class StorageProbeError(StorageError):
    """The storage cannot be used; the message says why, without any credential."""


def _endpoint_label(settings: Settings) -> str:
    """Host and port of the configured endpoint (never a user name or password), or AWS."""
    if not settings.s3_endpoint_url:
        return "AWS"
    parts = urlsplit(settings.s3_endpoint_url)
    return f"{parts.hostname}:{parts.port}" if parts.port else str(parts.hostname)


def _probe_s3(settings: Settings) -> None:
    # Imported here so a server that keeps photos on disk never loads boto3.
    from src.storage import s3

    # Building the client can fail on a bad endpoint or region; the error text of those
    # carries the full URL, so only the exception's type is ever reported.
    try:
        client = s3.build_client(
            settings,
            connect_timeout=PROBE_TIMEOUT_SECONDS,
            read_timeout=PROBE_TIMEOUT_SECONDS,
            attempts=1,
        )
    except (ValueError, BotoCoreError) as error:
        raise _failure(settings, "client", type(error).__name__) from None
    key = new_private_key()
    _step(settings, "HeadBucket", lambda: client.head_bucket(Bucket=settings.s3_bucket))
    try:
        _step(
            settings,
            "PutObject",
            lambda: client.put_object(Bucket=settings.s3_bucket, Key=key, Body=_PROBE_BODY),
        )
    except StorageProbeError:
        # The provider may have stored the object before the call failed (a read timeout):
        # try to remove it, and keep the put's error as the one reported.
        with suppress(Exception):
            client.delete_object(Bucket=settings.s3_bucket, Key=key)
        raise
    _step(
        settings, "DeleteObject", lambda: client.delete_object(Bucket=settings.s3_bucket, Key=key)
    )


def _step(settings: Settings, name: str, call: Callable[[], object]) -> None:
    try:
        call()
    except ClientError as error:
        reason = str(error.response.get("Error", {}).get("Code") or "refused")
        raise _failure(settings, name, reason) from None
    except BotoCoreError as error:
        raise _failure(settings, name, type(error).__name__) from None


def _failure(settings: Settings, step: str, reason: str) -> StorageProbeError:
    return StorageProbeError(
        f"the S3 bucket {settings.s3_bucket} at {_endpoint_label(settings)} cannot be used: "
        f"{step} failed ({reason})"
    )


def _probe_local(settings: Settings) -> None:
    """Development and test only: the folder is made when missing, then written and cleaned."""
    if settings.environment == Environment.PRODUCTION:
        message = "production keeps photos in S3, not on the local disk"
        raise StorageProbeError(message)
    folder = settings.local_media_path
    probe_file = folder / f".probe-{secrets.token_hex(8)}"
    try:
        make_private_folders(folder)
        descriptor = os.open(probe_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_PROBE_BODY)
        probe_file.unlink()
    except OSError as error:
        probe_file.unlink(missing_ok=True)
        message = f"the process cannot write to the photo folder {folder} ({type(error).__name__})"
        raise StorageProbeError(message) from None


def probe_storage(settings: Settings) -> None:
    """Raise `StorageProbeError` when the resolved store cannot be written to and cleaned up."""
    if settings.resolved_storage_backend == "s3":
        _probe_s3(settings)
    else:
        _probe_local(settings)


async def check_storage(settings: Settings) -> None:
    """Probe at start: production raises, anywhere else a warning is logged and the start goes on."""
    try:
        await asyncio.to_thread(probe_storage, settings)
    except StorageProbeError as error:
        if settings.environment == Environment.PRODUCTION:
            raise
        log.warning("Photo storage is not usable: %s.", error)
