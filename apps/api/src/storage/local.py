"""
Photo storage on the local disk, for development and for a server with no S3 bucket (decision 44).

Objects live under `LOCAL_MEDIA_DIR` (`data/media` of the checkout, gitignored, by default), in
`private/` and `public/`, with a two-digit subfolder taken from the random id so no folder grows
without bound. Files are written with owner-only permissions, to a temporary name first and
renamed into place, so a reader never sees half a photo.

There is no web server in front of a folder, so a "signed" link points at the API's
`/media/<key>` address with an expiry and an HMAC of both. The route that serves it (not
written yet; no photo is stored by any route yet) must call `verify_signature` before it reads
the file, and may serve a `public/` key without one.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import secrets
from pathlib import Path
from urllib.parse import urlencode

from src import clock
from src.config import checkout_root
from src.storage.base import (
    CONTENT_TYPE,
    KEY,
    InvalidKeyError,
    ObjectNotFoundError,
    check_key,
    check_object,
    check_ttl,
    is_public_key,
    split_key,
)

MEDIA_ROUTE = "/media"


def default_media_root() -> Path:
    """Return `data/media` of the checkout; the working directory's own `data/media` otherwise."""
    return checkout_root() / "data" / "media"


def make_private_folders(folder: Path) -> None:
    """Make `folder` and each missing parent at 0o700, whatever the process's umask or `parents`."""
    missing = [folder, *folder.parents]
    missing = missing[: next((i for i, p in enumerate(missing) if p.exists()), len(missing))]
    for each in reversed(missing):
        each.mkdir(mode=0o700, exist_ok=True)
        each.chmod(0o700)


class LocalStorage:
    """
    Implements `Storage` on a folder.

    `base_url` is the API's public address, which the links point at. `signing_key` signs them;
    it comes from the settings' own secret, so a link made on one installation is no good on
    another.
    """

    def __init__(
        self, root: Path, *, base_url: str, signing_key: bytes, default_ttl_seconds: int
    ) -> None:
        self.root = root
        self.base_url = base_url.rstrip("/")
        self._key = hashlib.sha256(b"tabsira-media-url:" + signing_key).digest()
        self.default_ttl_seconds = default_ttl_seconds

    def _path(self, key: str) -> Path:
        prefix, identifier = split_key(key)
        return self.root / prefix / identifier[:2] / f"{identifier}.jpg"

    # ─── Objects ─────────────────────────────────────────────────────────────

    async def put(self, key: str, data: bytes, *, content_type: str = CONTENT_TYPE) -> None:
        check_object(key, data, content_type)
        await asyncio.to_thread(self._write, self._path(key), data)

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError:
            message = "no object under that key"
            raise ObjectNotFoundError(message) from None

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._path(key).is_file)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._path(key).unlink, True)

    async def copy(self, source: str, destination: str) -> None:
        data = await self.get(source)
        await self.put(destination, data)

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        make_private_folders(path.parent)
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
            temporary.replace(path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    # ─── Addresses ───────────────────────────────────────────────────────────

    def _signature(self, key: str, expires: int) -> str:
        return hmac.new(self._key, f"{key}\n{expires}".encode(), hashlib.sha256).hexdigest()

    def signed_url(self, key: str, *, ttl_seconds: int | None = None) -> str:
        check_key(key)
        ttl = check_ttl(self.default_ttl_seconds if ttl_seconds is None else ttl_seconds)
        expires = int(clock.utcnow().timestamp()) + ttl
        query = urlencode({"expires": expires, "signature": self._signature(key, expires)})
        return f"{self.base_url}{MEDIA_ROUTE}/{key}?{query}"

    def verify_signature(self, key: str, expires: int, signature: str) -> bool:
        """Whether a link's `expires` and `signature` are genuine for `key` and still in time."""
        if KEY.fullmatch(key) is None or expires < int(clock.utcnow().timestamp()):
            return False
        return hmac.compare_digest(self._signature(key, expires), signature)

    def public_url(self, key: str) -> str:
        if not is_public_key(key):
            message = "only a published copy has a public address"
            raise InvalidKeyError(message)
        return f"{self.base_url}{MEDIA_ROUTE}/{key}"
