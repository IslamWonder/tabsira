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
from src.deps import DbDep, SettingsDep
from src.errors import AppError, ErrorCode
from src.models import Insight
from src.owner import INSIGHT, OptionalOwner, Owner, not_found
from src.scans.deps import CHAT_LIMITS, PublicIdPath, address_limit, feature
from src.schemas.insight import (
    ActionIn,
    ActionOut,
    ChatIn,
    ChatReply,
    CompletionOut,
    InsightDetailOut,
)
from src.services import chat_service, completion_service, insight_view

router = APIRouter(prefix="/insights", tags=["insights"])

ClientFactory = Callable[[CallLog], ModelClient]


def model_client_factory(request: Request, settings: SettingsDep) -> ClientFactory:
    """Return the factory of provider clients: a test's, or one on the process's HTTP client."""
    factory: ClientFactory | None = getattr(request.app.state, "model_client_factory", None)
    if factory is not None:
        return factory
    http: httpx.AsyncClient | None = getattr(request.app.state, "http", None)
    if http is None:
        http = httpx.AsyncClient()
        request.app.state.http = http
    shared = http

    def build(log: CallLog) -> ModelClient:
        return client_for(settings, shared, log=log)

    return build


ClientFactoryDep = Annotated[ClientFactory, Depends(model_client_factory)]


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
    _owner, insight = await owned_insight(db, owner, insight_id)
    return await insight_view.describe(db, settings, insight)


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
) -> ChatReply:
    """
    Answer a question classified by its content level, grounded in the insight.

    The same `idempotencyKey` returns the same answer and counts once; the
    fourth successful message answers 409 CHAT_LIMIT_REACHED.
    """
    _owner, insight = await owned_insight(db, owner, insight_id)
    return await chat_service.answer(
        db,
        settings,
        insight,
        question=body.message,
        key=body.idempotency_key,
        client_factory=client_factory,
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
    insight_id: PublicIdPath, db: DbDep, settings: SettingsDep, owner: OptionalOwner
) -> CompletionOut:
    """Complete the insight; a second call saves nothing more and answers the same place."""
    found, insight = await owned_insight(db, owner, insight_id)
    try:
        return await completion_service.complete(db, settings, found, insight)
    except SQLAlchemyError:
        await db.rollback()
        raise AppError(
            ErrorCode.SAVE_FAILED, "The insight was not saved.", status_code=503
        ) from None
