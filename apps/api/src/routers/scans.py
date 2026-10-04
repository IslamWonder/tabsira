"""
Scans: a photo in, insights out, by a background job with honest progress.

`POST /scans` takes a photo (multipart, field `image`) or its address (JSON
`{url}`, fetched by the server under v2 §6's limits), checks and strips it,
keeps it in the temporary store, and queues the job; it answers 202 at once.
`GET /scans/{id}/events` streams the job's progress (server-sent events, with
`Last-Event-ID` replay), from any API worker. `POST /scans/{id}/focus` and
`/clarify` run the engine again on the scene already understood. Only the owner
(account or guest) reaches a scan; anyone else gets the 404 of a scan that
does not exist. The photo goes to the AI provider for analysis
(docs/PRIVACY.md); a sensitive scene's photo is never returned nor kept.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import Response
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette import EventSourceResponse
from starlette.datastructures import UploadFile

from src import clock, messages
from src.config import Settings
from src.database import get_db
from src.deps import DbDep, SettingsDep
from src.errors import AppError, ErrorCode
from src.models import Insight, Scan, ScanOutcome, ScanSource, ScanStatus
from src.owner import SCAN, OptionalOwner, Owner, WritingOwner, not_found
from src.pipeline.engine import RelationType
from src.pipeline.image_validator import ImageRejectedCode, ImageRejectedError, validate_image
from src.pipeline.schemas import BBox, ImageUpload, SceneAnalysis, ValidatedImage
from src.scans import buffer, progress
from src.scans.deps import FetcherDep, QueueDep, RedisDep
from src.scans.fetch import FetchError, FetchRefusal
from src.scans.queue import QueueUnavailableError, ScanQueue
from src.schemas.scan import (
    ClarifyIn,
    FocusIn,
    InsightSummary,
    ScanEntityOut,
    ScanFromUrl,
    ScanImageOut,
    ScanOut,
)

router = APIRouter(prefix="/scans", tags=["scans"])

# Room for the multipart envelope around a photo of the largest size.
ENVELOPE_BYTES = 64 * 1024
IMAGE_ERRORS: dict[ImageRejectedCode, tuple[ErrorCode, int]] = {
    ImageRejectedCode.EMPTY: (ErrorCode.IMAGE_EMPTY, status.HTTP_400_BAD_REQUEST),
    ImageRejectedCode.TOO_LARGE: (ErrorCode.IMAGE_TOO_LARGE, status.HTTP_413_CONTENT_TOO_LARGE),
    ImageRejectedCode.TOO_SMALL: (ErrorCode.IMAGE_TOO_SMALL, status.HTTP_400_BAD_REQUEST),
    ImageRejectedCode.UNSUPPORTED: (
        ErrorCode.IMAGE_UNSUPPORTED,
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    ),
    ImageRejectedCode.INVALID: (ErrorCode.IMAGE_INVALID, status.HTTP_400_BAD_REQUEST),
}
URL_REFUSALS = frozenset(
    {FetchRefusal.INVALID_URL, FetchRefusal.FORBIDDEN_ADDRESS, FetchRefusal.TOO_MANY_REDIRECTS}
)
UPLOAD_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["image"],
                    "properties": {"image": {"type": "string", "format": "binary"}},
                }
            },
            "application/json": {"schema": {"$ref": "#/components/schemas/ScanFromUrl"}},
        },
    }
}
# The stream closes its function-scoped session before the first event: an open
# tab must not hold a database connection for as long as it stays open.
StreamDb = Annotated[AsyncSession, Depends(get_db, scope="function")]


def _queue_unavailable() -> AppError:
    return AppError(
        ErrorCode.QUEUE_UNAVAILABLE,
        "The scan cannot be started now.",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


async def _photo_bytes(
    request: Request, settings: Settings, fetch: FetcherDep
) -> tuple[bytes, ScanSource]:
    content_type = request.headers.get("content-type", "").lower()
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > settings.image_max_bytes + ENVELOPE_BYTES:
        raise AppError(
            ErrorCode.IMAGE_TOO_LARGE,
            "The photo is larger than the limit.",
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        )
    if content_type.startswith("multipart/form-data"):
        async with request.form(max_files=1, max_fields=1) as form:
            upload = form.get("image")
            if not isinstance(upload, UploadFile):
                raise AppError(ErrorCode.IMAGE_EMPTY, "Send the photo in the field `image`.")
            data = await upload.read(settings.image_max_bytes + 1)
        return data, ScanSource.UPLOAD
    if content_type.startswith("application/json"):
        try:
            body = ScanFromUrl.model_validate_json(await request.body())
        except ValidationError:
            raise AppError(ErrorCode.VALIDATION_ERROR, "Send {url}.", status_code=422) from None
        try:
            return await fetch(body.url), ScanSource.URL
        except FetchError as refusal:
            raise _fetch_error(refusal) from None
    raise AppError(
        ErrorCode.UNSUPPORTED_MEDIA_TYPE,
        "Send a multipart photo or a JSON {url}.",
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    )


def _fetch_error(refusal: FetchError) -> AppError:
    if refusal.refusal is FetchRefusal.TOO_LARGE:
        return AppError(
            ErrorCode.IMAGE_TOO_LARGE,
            refusal.detail,
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        )
    if refusal.refusal in URL_REFUSALS:
        return AppError(ErrorCode.IMAGE_URL_REFUSED, refusal.refusal.value)
    return AppError(
        ErrorCode.IMAGE_FETCH_FAILED,
        refusal.refusal.value,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


async def _validated(data: bytes, settings: Settings) -> ValidatedImage:
    try:
        return await anyio.to_thread.run_sync(
            lambda: validate_image(
                ImageUpload(data=data),
                max_bytes=settings.image_max_bytes,
                max_pixels=settings.image_max_pixels,
            )
        )
    except ImageRejectedError as rejected:
        code, http_status = IMAGE_ERRORS[rejected.code]
        raise AppError(code, rejected.detail, status_code=http_status) from None


async def _owned_scan(db: AsyncSession, owner: Owner | None, scan_id: uuid.UUID) -> Scan:
    if owner is None:
        raise not_found(SCAN)
    scan: Scan | None = await db.scalar(select(Scan).where(Scan.id == scan_id, owner.where(Scan)))
    if scan is None:
        raise not_found(SCAN)
    return scan


async def describe(db: AsyncSession, scan: Scan, redis: RedisDep) -> ScanOut:
    """Return what the owner sees of a scan; never the photo of a sensitive scene."""
    scene = SceneAnalysis.model_validate(scan.scene) if scan.scene else None
    insights = (
        await db.scalars(
            select(Insight)
            .where(Insight.scan_id == scan.id)
            .order_by(Insight.run.desc(), Insight.position)
        )
    ).all()
    available = False
    if not scan.sensitive:
        try:
            available = bool(await redis.exists(f"scan:{scan.id}:{buffer.Copy.FULL.value}"))
        except RedisError:
            available = False
    return ScanOut(
        id=scan.id,
        status=scan.status,
        outcome=scan.outcome,
        error_code=scan.error_code,
        run=scan.run,
        engine=scan.engine,
        engine_label=messages.DEMO_ENGINE if scan.engine == "demo" else None,
        source=scan.source,
        sensitive=scan.sensitive,
        image=ScanImageOut(
            available=available,
            width=None if scan.sensitive else scan.image_width,
            height=None if scan.sensitive else scan.image_height,
            url=f"/scans/{scan.id}/image" if available else None,
        ),
        description=scene.description if scene else None,
        entities=[
            ScanEntityOut(
                id=entity.id,
                label_arabic=entity.label_arabic,
                bbox=entity.bbox,
                origin=entity.origin,
                status=entity.status,
            )
            for entity in (scene.entities if scene else [])
        ],
        clarification_question=scan.clarification_question,
        insights=[
            InsightSummary(
                id=insight.id,
                title=insight.title,
                glimpse=insight.glimpse,
                anchor=BBox.model_validate(insight.anchor) if insight.anchor else None,
                relation=RelationType(insight.relation),
                relation_label=messages.RELATION_LABELS[insight.relation],
                completed=insight.completed_at is not None,
            )
            for insight in insights
        ],
        awaiting_verification=len(scan.awaiting_ruling),
        events_url=f"/scans/{scan.id}/events",
        created_at=scan.created_at,
        finished_at=scan.finished_at,
        disclosure=messages.AI_DISCLOSURE,
    )


async def _queue(
    db: AsyncSession, redis: RedisDep, queue: ScanQueue, settings: Settings, scan: Scan
) -> None:
    """Announce and queue the scan's current run; a queue that is down fails the scan honestly."""
    try:
        await progress.publish(
            redis, scan.id, "queued", {"run": scan.run}, ttl=settings.scan_events_ttl_seconds
        )
        await queue.enqueue(scan.id, scan.run)
    except (RedisError, QueueUnavailableError):
        scan.status = ScanStatus.FAILED
        scan.error_code = ErrorCode.QUEUE_UNAVAILABLE.value
        scan.finished_at = clock.utcnow()
        await db.commit()
        raise _queue_unavailable() from None


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a scan of a photo or of a photo's address",
    openapi_extra=UPLOAD_BODY,
)
async def create_scan(
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    owner: WritingOwner,
    redis: RedisDep,
    queue: QueueDep,
    fetch: FetcherDep,
) -> ScanOut:
    """Check the photo, keep it for an hour, queue the scan and answer at once."""
    data, source = await _photo_bytes(request, settings, fetch)
    image = await _validated(data, settings)
    scan = Scan(
        **owner.columns(),
        source=source,
        status=ScanStatus.QUEUED,
        engine=settings.scan_engine.value,
        image_width=image.image.width,
        image_height=image.image.height,
    )
    db.add(scan)
    await db.flush()
    try:
        await buffer.put(
            redis,
            scan.id,
            full=image.image,
            model=image.model_image,
            ttl=settings.scan_image_ttl_seconds,
        )
    except RedisError:
        await db.rollback()
        raise _queue_unavailable() from None
    await db.commit()
    await _queue(db, redis, queue, settings, scan)
    return await describe(db, scan, redis)


@router.get("/{scan_id}", summary="A scan and what it found")
async def get_scan(scan_id: uuid.UUID, db: DbDep, owner: OptionalOwner, redis: RedisDep) -> ScanOut:
    """Return the owner's scan: its state, its scene and its insights."""
    return await describe(db, await _owned_scan(db, owner, scan_id), redis)


@router.get(
    "/{scan_id}/image",
    summary="The stripped photo of a scan, while it is kept",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
async def get_scan_image(
    scan_id: uuid.UUID, db: DbDep, owner: OptionalOwner, redis: RedisDep
) -> Response:
    """Return the photo without its metadata to its owner, for the hour it is kept."""
    scan = await _owned_scan(db, owner, scan_id)
    data = None if scan.sensitive else await buffer.get(redis, scan.id, buffer.Copy.FULL)
    if data is None:
        raise AppError(
            ErrorCode.ASSET_MISSING,
            "The photo is not kept.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get(
    "/{scan_id}/events",
    summary="The progress of a scan, as server-sent events",
    response_class=EventSourceResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def scan_events(
    scan_id: uuid.UUID,
    db: StreamDb,
    settings: SettingsDep,
    owner: OptionalOwner,
    redis: RedisDep,
    last_event_id: Annotated[str | None, Header()] = None,
) -> EventSourceResponse:
    """
    Stream `queued`, `stage`, then `done` or `failed` for the scan's current run.

    A reader that reconnects sends `Last-Event-ID` and gets only what it missed.
    """
    scan = await _owned_scan(db, owner, scan_id)
    fallback = None
    if scan.status is ScanStatus.DONE:
        fallback = progress.ProgressEvent(
            id=0,
            event="done",
            data={
                "run": scan.run,
                "outcome": (scan.outcome or ScanOutcome.NO_RELEVANT_EVIDENCE).value,
            },
        )
    elif scan.status is ScanStatus.FAILED:
        fallback = progress.ProgressEvent(
            id=0, event="failed", data={"run": scan.run, "code": scan.error_code}
        )
    events = progress.stream(
        redis,
        scan.id,
        run=scan.run,
        after=progress.parse_last_event_id(last_event_id),
        fallback=fallback,
        max_seconds=settings.scan_job_timeout_seconds + 60,
    )

    async def sse() -> Any:
        async for event in events:
            yield event.as_sse()

    return EventSourceResponse(
        sse(), ping=15, headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
    )


def _ensure_rerunnable(scan: Scan) -> None:
    """Refuse a new run while one runs, or when the scene was never understood."""
    if scan.status in {ScanStatus.QUEUED, ScanStatus.RUNNING}:
        raise AppError(ErrorCode.SCAN_BUSY, "The scan is still running.", status_code=409)
    if scan.scene is None:
        raise AppError(
            ErrorCode.ASSET_MISSING, "The scene of this scan was never understood.", status_code=409
        )


async def _rerun(
    db: AsyncSession,
    redis: RedisDep,
    queue: ScanQueue,
    settings: Settings,
    scan: Scan,
    **changes: Any,
) -> ScanOut:
    for name, value in changes.items():
        setattr(scan, name, value)
    scan.run += 1
    scan.status = ScanStatus.QUEUED
    scan.outcome = None
    scan.error_code = None
    scan.finished_at = None
    await db.commit()
    await _queue(db, redis, queue, settings, scan)
    return await describe(db, scan, redis)


@router.post(
    "/{scan_id}/focus",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Point at one thing in the scene and look again",
)
async def focus_scan(
    scan_id: uuid.UUID,
    body: FocusIn,
    db: DbDep,
    settings: SettingsDep,
    owner: OptionalOwner,
    redis: RedisDep,
    queue: QueueDep,
) -> ScanOut:
    """Run the engine again on the thing the learner chose or the box they drew."""
    scan = await _owned_scan(db, owner, scan_id)
    _ensure_rerunnable(scan)
    if body.entity_id is not None:
        scene = SceneAnalysis.model_validate(scan.scene)
        if body.entity_id not in {entity.id for entity in scene.entities}:
            raise AppError(
                ErrorCode.VALIDATION_ERROR, "The scene has no such thing.", status_code=422
            )
        focus: dict[str, Any] = {"entity_id": body.entity_id}
    else:
        focus = {"box": body.box.model_dump() if body.box else None, "label": body.label}
    return await _rerun(db, redis, queue, settings, scan, focus=focus, clarification_question=None)


@router.post(
    "/{scan_id}/clarify",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Answer the one question the scan asked",
)
async def clarify_scan(
    scan_id: uuid.UUID,
    body: ClarifyIn,
    db: DbDep,
    settings: SettingsDep,
    owner: OptionalOwner,
    redis: RedisDep,
    queue: QueueDep,
) -> ScanOut:
    """Run the engine again with the learner's answer."""
    scan = await _owned_scan(db, owner, scan_id)
    _ensure_rerunnable(scan)
    if scan.outcome is not ScanOutcome.NEEDS_CLARIFICATION:
        raise AppError(ErrorCode.CONFLICT, "The scan asked no question.", status_code=409)
    return await _rerun(db, redis, queue, settings, scan, clarification_answer=body.answer.strip())
