"""
The sound effects of the ontology: one short MP3 per entity, kept apart from the photos.

They are static files that the owners upload once under `static/ontology/audio/<id>.mp3` in the
bucket (decision 8's bucket; no photo ever lives under `static/`). The API reads them and serves
them itself, so the browser only ever talks to the API's own host and the bucket stays private.
With no bucket, a development machine reads the same path under `LOCAL_MEDIA_DIR`.

An id is checked against `ENTITY_ID` before it reaches a path or an object name.
"""

from __future__ import annotations

import asyncio
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from src.config import Settings
from src.storage.base import InvalidKeyError, ObjectNotFoundError, StorageUnavailableError

SOUND_PREFIX = "static/ontology/audio"
SOUND_CONTENT_TYPE = "audio/mpeg"
# The ids of the ontology workbook: E001 to E999, then E1000.
ENTITY_ID = re.compile(r"^E[0-9]{3,4}$")
# A day: the files change only when the owners upload new ones.
SOUND_CACHE_CONTROL = "public, max-age=86400"
# Sounds are about 150 KB each; this many at once is a few megabytes of memory per worker.
KEPT_SOUNDS = 64
_NOT_FOUND_CODES = frozenset({"NoSuchKey", "NotFound", "404"})
_NO_SOUND = "no sound under that key"
_NOT_ANSWERING = "the sound storage did not answer"


def sound_key(entity_id: str) -> str:
    """Return the object key of an entity's sound; raise `InvalidKeyError` for anything else."""
    if ENTITY_ID.fullmatch(entity_id) is None:
        message = "not an ontology entity id"
        raise InvalidKeyError(message)
    return f"{SOUND_PREFIX}/{entity_id}.mp3"


class SoundStore:
    """Reads the sound of an entity from the bucket, or from the local folder without one."""

    def __init__(self, *, bucket: str, client: Any, root: Path) -> None:
        self.bucket = bucket
        self.client = client
        self.root = root
        self._kept: OrderedDict[str, bytes] = OrderedDict()

    @classmethod
    def from_settings(cls, settings: Settings) -> SoundStore:
        """Build the store the photo settings describe; boto3 is loaded only for a bucket."""
        if settings.resolved_storage_backend == "s3":
            from src.storage.s3 import build_client

            return cls(
                bucket=settings.s3_bucket,
                client=build_client(settings),
                root=settings.local_media_path,
            )
        return cls(bucket="", client=None, root=settings.local_media_path)

    async def get(self, entity_id: str) -> bytes:
        """Return the MP3, or raise `ObjectNotFoundError` when none was uploaded for the entity."""
        key = sound_key(entity_id)
        if key in self._kept:
            self._kept.move_to_end(key)
            return self._kept[key]
        data = await (self._from_bucket(key) if self.client else self._from_disk(key))
        self._kept[key] = data
        if len(self._kept) > KEPT_SOUNDS:
            self._kept.popitem(last=False)
        return data

    async def _from_disk(self, key: str) -> bytes:
        try:
            return await asyncio.to_thread((self.root / key).read_bytes)
        except OSError:
            raise ObjectNotFoundError(_NO_SOUND) from None

    async def _from_bucket(self, key: str) -> bytes:
        def read() -> bytes:
            body: bytes = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
            return body

        try:
            return await asyncio.to_thread(read)
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in _NOT_FOUND_CODES or status == 404:
                raise ObjectNotFoundError(_NO_SOUND) from None
            raise StorageUnavailableError(_NOT_ANSWERING) from None
        except BotoCoreError:
            raise StorageUnavailableError(_NOT_ANSWERING) from None
