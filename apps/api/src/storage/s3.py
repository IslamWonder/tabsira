"""
Photo storage in a private S3-compatible bucket, for production (decision 8).

The bucket is private. Every owner's copy is under `private/`, reachable only through a signed
link that expires within minutes. A copy under `public/` exists only while its owner keeps the
photo published; `S3_PUBLIC_BASE_URL` is where that prefix, and nothing else, is served from
(a CDN, or a bucket policy that makes `public/*` readable). Nothing here ever sets an object
public: whether a key is readable by anyone is decided by where it is, not by a flag.

boto3 is synchronous, so each call that waits on the network runs in a worker thread. Signing a
link is only arithmetic and runs inline. A failed call is translated into this package's own
errors; the original is logged without the bucket, the key or any credential.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from src.config import Settings
from src.storage.base import (
    CONTENT_TYPE,
    InvalidKeyError,
    ObjectNotFoundError,
    StorageUnavailableError,
    check_key,
    check_object,
    check_owner_prefix,
    check_ttl,
    is_public_key,
)

log = logging.getLogger("tabsira.storage")

# An owner's copy must never be cached by anything between the bucket and the owner; a published
# copy is deleted when it is withdrawn, so it is cached for five minutes at most and is never
# marked immutable: that is how long a withdrawn photo can linger, as the privacy text says.
PRIVATE_CACHE_CONTROL = "private, no-store"
# S3 lists and deletes at most a thousand keys a call.
DELETE_BATCH = 1000
PUBLIC_CACHE_CONTROL = "public, max-age=300"
_NOT_FOUND_CODES = frozenset({"NoSuchKey", "NotFound", "404"})


def _cache_control(key: str) -> str:
    return PUBLIC_CACHE_CONTROL if is_public_key(key) else PRIVATE_CACHE_CONTROL


def _translate(error: Exception) -> Exception:
    """Return the storage error for a boto failure, and log what failed without any detail."""
    if isinstance(error, ClientError):
        code = str(error.response.get("Error", {}).get("Code", ""))
        status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in _NOT_FOUND_CODES or status == 404:
            return ObjectNotFoundError("no object under that key")
        log.warning("Storage call refused: %s (HTTP %s).", code or "unknown", status)
    else:
        log.warning("Storage call failed: %s.", type(error).__name__)
    return StorageUnavailableError("the photo storage did not answer")


def build_client(
    settings: Settings, *, connect_timeout: int = 3, read_timeout: int = 10, attempts: int = 4
) -> Any:
    """Build the boto3 client of the `S3_*` settings; the start-up probe asks for shorter waits."""
    endpoint = settings.s3_endpoint_url or None
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        config=Config(
            signature_version="s3v4",
            # Another provider's endpoint rarely serves a bucket under its own host name.
            s3={"addressing_style": "path" if endpoint else "auto"},
            retries={"max_attempts": attempts - 1, "mode": "standard"},
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
        ),
    )


class S3Storage:
    """Implements `Storage` on one bucket."""

    def __init__(
        self,
        *,
        bucket: str,
        public_base_url: str,
        default_ttl_seconds: int,
        client: Any,
    ) -> None:
        self.bucket = bucket
        self.public_base_url = public_base_url.rstrip("/")
        self.default_ttl_seconds = default_ttl_seconds
        self.client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> S3Storage:
        """Build the store and its client from the `S3_*` settings."""
        return cls(
            bucket=settings.s3_bucket,
            public_base_url=settings.s3_public_base_url,
            default_ttl_seconds=settings.signed_url_ttl_seconds,
            client=build_client(settings),
        )

    async def _call(self, operation: str, **arguments: Any) -> Any:
        """Run one client operation in a thread and translate what goes wrong."""
        method = getattr(self.client, operation)
        try:
            return await asyncio.to_thread(method, Bucket=self.bucket, **arguments)
        except (ClientError, BotoCoreError) as error:
            raise _translate(error) from None

    # ─── Objects ─────────────────────────────────────────────────────────────

    async def put(self, key: str, data: bytes, *, content_type: str = CONTENT_TYPE) -> None:
        check_object(key, data, content_type)
        await self._call(
            "put_object",
            Key=key,
            Body=data,
            ContentType=content_type,
            CacheControl=_cache_control(key),
        )

    async def get(self, key: str) -> bytes:
        response = await self._call("get_object", Key=check_key(key))
        body: bytes = await asyncio.to_thread(response["Body"].read)
        return body

    async def exists(self, key: str) -> bool:
        try:
            await self._call("head_object", Key=check_key(key))
        except ObjectNotFoundError:
            return False
        return True

    async def delete(self, key: str) -> None:
        # S3 answers 204 for a key that is not there, so this is idempotent as is.
        await self._call("delete_object", Key=check_key(key))

    async def delete_prefix(self, prefix: str) -> int:
        check_owner_prefix(prefix)
        removed = 0
        token: str | None = None
        while True:
            listing = await self._call(
                "list_objects_v2",
                Prefix=prefix,
                MaxKeys=DELETE_BATCH,
                **({} if token is None else {"ContinuationToken": token}),
            )
            keys = [item["Key"] for item in listing.get("Contents", [])]
            if keys:
                answer = await self._call(
                    "delete_objects",
                    Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
                )
                if answer.get("Errors"):
                    message = "some objects of the folder could not be deleted"
                    raise StorageUnavailableError(message)
                removed += len(keys)
            if not listing.get("IsTruncated"):
                return removed
            token = listing.get("NextContinuationToken")

    async def copy(self, source: str, destination: str) -> None:
        check_key(source)
        check_key(destination)
        await self._call(
            "copy_object",
            Key=destination,
            CopySource={"Bucket": self.bucket, "Key": source},
            # The copy gets its own headers: a published copy is cacheable, the original is not.
            MetadataDirective="REPLACE",
            ContentType=CONTENT_TYPE,
            CacheControl=_cache_control(destination),
        )

    # ─── Addresses ───────────────────────────────────────────────────────────

    def signed_url(self, key: str, *, ttl_seconds: int | None = None) -> str:
        check_key(key)
        ttl = check_ttl(self.default_ttl_seconds if ttl_seconds is None else ttl_seconds)
        url: str = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=ttl,
            HttpMethod="GET",
        )
        return url

    def public_url(self, key: str) -> str:
        if not is_public_key(key):
            message = "only a published copy has a public address"
            raise InvalidKeyError(message)
        return f"{self.public_base_url}/{key}"
