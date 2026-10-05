"""
An insight and what its owner does with it: read it, ask about it, declare its step, complete it.

Every route answers only the owner (account or guest); another owner's insight
answers the 404 of one that does not exist. Scripture is read from the store
by reference on every read; nothing a model wrote is shown as Quran or hadith.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock
from src.ai.client import ModelClient, client_for
from src.ai.records import CallLog
from src.deps import DbDep, PhotoStoreDep, SettingsDep, UngatedCurrentUser, VerifiedUser, limited
from src.errors import AppError, ErrorCode
from src.models import Insight
from src.owner import INSIGHT, OptionalOwner, Owner, not_found
from src.pipeline.insight.engine import SHARED_RESOURCES, ResourceCache
from src.scans.deps import CHAT_LIMITS, PublicIdPath, RedisDep, address_limit, feature
from src.schemas.insight import (
    ActionIn,
    ActionOut,
    ChatIn,
    ChatReply,
    CompletionOut,
    InsightDetailOut,
    PublicationOut,
)
from src.services import (
    account_gate,
    chat_service,
    completion_service,
    insight_view,
    public_insight_service,
)
from src.services.social_limits import WriteKind

router = APIRouter(prefix="/insights", tags=["insights"])

ClientFactory = Callable[[CallLog], ModelClient]


def shared_http(request: Request) -> httpx.AsyncClient:
    """Return the process's HTTP client, opened on first use and closed with the app."""
    http: httpx.AsyncClient | None = getattr(request.app.state, "http", None)
    if http is None:
        http = httpx.AsyncClient()
        request.app.state.http = http
    return http


def model_client_factory(request: Request, settings: SettingsDep) -> ClientFactory:
    """Return the factory of provider clients: a test's, or one on the process's HTTP client."""
    factory: ClientFactory | None = getattr(request.app.state, "model_client_factory", None)
    if factory is not None:
        return factory
    shared = shared_http(request)

    def build(log: CallLog) -> ModelClient:
        return client_for(settings, shared, log=log)

    return build


def engine_resources(request: Request) -> ResourceCache:
    """Return the engine's shared indexes and shingles: a test's, or the process's."""
    resources: ResourceCache | None = getattr(request.app.state, "engine_resources", None)
    return resources if resources is not None else SHARED_RESOURCES


ClientFactoryDep = Annotated[ClientFactory, Depends(model_client_factory)]
HttpDep = Annotated[httpx.AsyncClient, Depends(shared_http)]
ResourcesDep = Annotated[ResourceCache, Depends(engine_resources)]


async def owned_insight(
    db: AsyncSession, owner: Owner | None, insight_id: int
) -> tuple[Owner, Insight]:
    """Return the owner and their insight, or the 404 of an insight that does not exist."""
    if owner is None:
        raise not_found(INSIGHT)
    insight: Insight | None = await db.scalar(
        select(Insight).where(Insight.id == insight_id, owner.where(Insight))
    )
    if insight is None:
        raise not_found(INSIGHT)
    return owner, insight


@router.get("/{insight_id}", summary="One insight, its scripture read from the store")
async def get_insight(
    insight_id: PublicIdPath, db: DbDep, settings: SettingsDep, owner: OptionalOwner
) -> InsightDetailOut:
    """Return the insight: its verse and hadith exactly as stored, the explanation apart."""
    holder, insight = await owned_insight(db, owner, insight_id)
    return await insight_view.describe(db, settings, insight, holder)


@router.post(
    "/{insight_id}/chat",
    summary="Ask one question about the insight (three at most)",
    dependencies=[
        Depends(feature("chat")),
        Depends(address_limit(CHAT_LIMITS, "Too many questions. Try again later.")),
    ],
)
async def chat(
    insight_id: PublicIdPath,
    body: ChatIn,
    db: DbDep,
    settings: SettingsDep,
    owner: OptionalOwner,
    client_factory: ClientFactoryDep,
    http: HttpDep,
    resources: ResourcesDep,
) -> ChatReply:
    """
    Answer a question classified by its content level, grounded in the insight.

    The same `idempotencyKey` returns the same answer and counts once; the
    fourth successful message answers 409 CHAT_LIMIT_REACHED. A request for
    another text runs the retrieval and the verification again (v2 §14). 403
    `profile_required` for an account that has not completed its profile (decision 63).
    """
    held_by, insight = await owned_insight(db, owner, insight_id)
    await account_gate.require_profile(db, held_by)
    return await chat_service.answer(
        db,
        settings,
        insight,
        question=body.message,
        key=body.idempotency_key,
        client_factory=client_factory,
        http=http,
        resources=resources,
    )


@router.post("/{insight_id}/action", summary="Declare the small step done, or for later")
async def declare_action(
    insight_id: PublicIdPath, body: ActionIn, db: DbDep, owner: OptionalOwner
) -> ActionOut:
    """Record «نفّذته» or «سأفعله لاحقًا»: the learner's own statement, never a proof or a reward."""
    _owner, insight = await owned_insight(db, owner, insight_id)
    if insight.action_state is not body.choice:
        insight.action_state = body.choice
        insight.action_at = clock.utcnow()
        await db.commit()
    return ActionOut(
        state=insight.action_state,
        at=insight.action_at,
        means=insight_view.action_means(body.choice.value),
    )


@router.post("/{insight_id}/complete", summary="«تمّ»: complete the insight, once")
async def complete_insight(
    insight_id: PublicIdPath,
    db: DbDep,
    settings: SettingsDep,
    owner: OptionalOwner,
    redis: RedisDep,
    photos: PhotoStoreDep,
) -> CompletionOut:
    """
    Complete the insight; a second call saves nothing more and answers the same place.

    The first «تمّ» of a signed-in owner who consented to keep photos also keeps the scan's
    photo privately (v2 §19); nothing is kept for a guest or a sensitive scene.
    """
    found, insight = await owned_insight(db, owner, insight_id)
    try:
        return await completion_service.complete(
            db, settings, found, insight, redis=redis, photos=photos
        )
    except SQLAlchemyError:
        await db.rollback()
        raise AppError(
            ErrorCode.SAVE_FAILED, "The insight was not saved.", status_code=503
        ) from None


@router.put(
    "/{insight_id}/publication",
    summary="Make the insight public (verified owners)",
    dependencies=[Depends(feature("world")), limited(WriteKind.POST)],
)
async def publish_insight(
    insight_id: PublicIdPath, db: DbDep, user: VerifiedUser
) -> PublicationOut:
    """
    Publish the caller's own insight; asking again changes nothing.

    Answers 409 INSIGHT_NOT_PUBLISHABLE for a sensitive scene, an insight with no text to
    show from the store, text that looks like scripture, one shaped by the profile, or one that is not from the real
    analysis; 409 UNDER_13_CANNOT_PUBLISH when the account declared it is under 13 (v2 §5).
    A guest gets 401.
    """
    _owner, insight = await owned_insight(db, Owner(user_id=user.id), insight_id)
    return await public_insight_service.publish(db, insight)


@router.delete("/{insight_id}/publication", summary="Withdraw the insight from public view")
async def withdraw_insight(
    insight_id: PublicIdPath, db: DbDep, user: UngatedCurrentUser
) -> PublicationOut:
    """
    Take the caller's insight down at once; its public address answers 404 from then on.

    Withdrawing publishes nothing, so it needs neither a verified address nor the latest
    terms, and it is never switched off or rate limited.
    """
    _owner, insight = await owned_insight(db, Owner(user_id=user.id), insight_id)
    return await public_insight_service.withdraw(db, insight)
