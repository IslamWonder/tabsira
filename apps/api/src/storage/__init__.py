"""
Photo storage: the interface (`base`), the local-disk store, and the S3 store.

`build_storage(settings)` returns the one the settings resolve to (decision 44).
"""

from __future__ import annotations

from src.config import Settings
from src.storage.base import Storage, StorageConfigError
from src.storage.local import LocalStorage


def build_storage(settings: Settings) -> Storage:
    """
    Build the photo store the settings describe.

    S3 is imported only when it is chosen, so a development machine that keeps photos on disk
    never loads boto3. Production refuses the local store: a photo on the disk of one web
    server would be lost with it and invisible to the others (decision 44).
    """
    if settings.is_production and settings.resolved_storage_backend != "s3":
        message = "production keeps photos in S3: set STORAGE_BACKEND=s3 and the S3_* keys"
        raise StorageConfigError(message)
    if settings.resolved_storage_backend == "s3":
        from src.storage.s3 import S3Storage

        return S3Storage.from_settings(settings)
    return LocalStorage(
        settings.local_media_path,
        base_url=settings.api_url,
        signing_key=settings.hash_key,
        default_ttl_seconds=settings.signed_url_ttl_seconds,
    )
