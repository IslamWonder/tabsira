"""
The public copies of photos, served by the API from the photo store (decision 44, v2 §19).

On a development machine `LocalStorage.public_url` points at this route; in production
`S3_PUBLIC_BASE_URL=https://api.tabsira.me/media` does, so the bucket stays private (no bucket
policy, no address of the storage provider in the visitor's browser) and the API reads the copy
with its own keys. It serves `public/` keys and nothing else: a private copy has a signed address
of its own, and the key's shape is checked before the store is asked.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Response

from src.deps import PhotoStoreDep
from src.errors import AppError, ErrorCode
from src.storage.base import CONTENT_TYPE, PUBLIC_PREFIX, StorageError
from src.storage.local import MEDIA_ROUTE

router = APIRouter(tags=["media"])

# The same life as a published copy on S3 (docs/PRIVACY.md): a withdrawn photo may stay in a
# browser cache for up to five minutes, never longer.
CACHE_CONTROL = "public, max-age=300"
Name = Annotated[str, Path(pattern=r"^[0-9a-f]{32}\.jpg$")]


def _not_found() -> AppError:
    return AppError(ErrorCode.NOT_FOUND, "No such photo.", status_code=404)


@router.get(
    f"{MEDIA_ROUTE}/{PUBLIC_PREFIX}/{{name}}",
    summary="A photo's public copy",
    response_class=Response,
    responses={200: {"content": {CONTENT_TYPE: {}}}},
)
async def public_photo(name: Name, photos: PhotoStoreDep) -> Response:
    """Return the published copy under `public/<name>`; 404 when there is none."""
    try:
        data = await photos.storage.get(f"{PUBLIC_PREFIX}/{name}")
    except StorageError:
        raise _not_found() from None
    return Response(content=data, media_type=CONTENT_TYPE, headers={"Cache-Control": CACHE_CONTROL})
