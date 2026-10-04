"""The sound effect of an ontology entity: public, read-only, and cacheable by the browser."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Request, Response, status

from src.deps import SettingsDep
from src.errors import AppError, ErrorCode
from src.storage.base import ObjectNotFoundError, StorageUnavailableError
from src.storage.sounds import (
    SOUND_CACHE_CONTROL,
    SOUND_CONTENT_TYPE,
    SoundStore,
)

router = APIRouter(prefix="/sounds", tags=["sounds"])

EntityId = Annotated[str, Path(pattern=r"^E[0-9]{3,4}$", description="An ontology id such as E001")]


def sound_store(request: Request, settings: SettingsDep) -> SoundStore:
    """Return the process's store, built on first use so its small cache is shared."""
    store: SoundStore | None = getattr(request.app.state, "sound_store", None)
    if store is None:
        store = SoundStore.from_settings(settings)
        request.app.state.sound_store = store
    return store


@router.get(
    "/ontology/{entity_id}",
    summary="The sound effect of one ontology entity, as MP3",
    response_class=Response,
    responses={200: {"content": {SOUND_CONTENT_TYPE: {}}}},
)
async def ontology_sound(entity_id: EntityId, request: Request, settings: SettingsDep) -> Response:
    """Return `static/ontology/audio/<entity_id>.mp3` of the bucket; 404 when it was not uploaded."""
    try:
        data = await sound_store(request, settings).get(entity_id)
    except ObjectNotFoundError:
        raise AppError(
            ErrorCode.NOT_FOUND,
            "No sound is stored for this entity.",
            status_code=status.HTTP_404_NOT_FOUND,
        ) from None
    except StorageUnavailableError:
        raise AppError(
            ErrorCode.STORAGE_UNAVAILABLE,
            "The sounds cannot be read now.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from None
    return Response(
        content=data,
        media_type=SOUND_CONTENT_TYPE,
        headers={"Cache-Control": SOUND_CACHE_CONTROL},
    )
