"""
Editorial grading from dorar.net (decision 18): rulings, eligibility and the verification queue.

dorar.net is never called from the server. An editor opens it in a browser and
records the ruling exactly as dorar gives it, with the scholar, the book and
page, the dorar page address, and the editor's reading of it as one of five
classifications. Rulings are only ever added (the database refuses to change
or remove one); the latest is the one in force. A hadith is eligible as
evidence only when that latest ruling reads صحيح or حسن; a hadith the pipeline
wanted but that has no ruling yet waits in a queue ordered by demand, and the
insight shows its verse alone meanwhile. The dataset grades never decide.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Hadith, HadithClassification, HadithRuling, HadithVerificationQueue
from src.scripture.errors import ScriptureError

ELIGIBLE = frozenset({HadithClassification.SAHIH, HadithClassification.HASAN})
DORAR_HOSTS = frozenset({"dorar.net", "www.dorar.net"})


class RulingError(ScriptureError):
    """A ruling names no stored hadith."""


class RulingInput(BaseModel):
    """What an editor records from dorar.net; the ruling text is kept exactly as typed."""

    ruling_text: str
    scholar: str
    source_book: str
    page: str
    dorar_url: str
    classification: HadithClassification
    editor_name: str
    recorded_by: uuid.UUID | None = None

    @field_validator("ruling_text", "scholar", "source_book", "page", "editor_name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            message = "must not be blank"
            raise ValueError(message)
        return value

    @field_validator("dorar_url")
    @classmethod
    def _on_dorar(cls, value: str) -> str:
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or parts.hostname not in DORAR_HOSTS
            or not parts.path.strip("/")
        ):
            message = "must be the https address of a dorar.net page"
            raise ValueError(message)
        return value


@dataclass(frozen=True)
class QueuedHadith:
    hadith: Hadith
    demand_count: int
    first_requested_at: datetime
    last_requested_at: datetime


def classification_is_eligible(classification: HadithClassification | None) -> bool:
    return classification in ELIGIBLE


async def latest_ruling(session: AsyncSession, hadith_id: int) -> HadithRuling | None:
    """Return the ruling in force for a hadith: the last one recorded, or None."""
    result: HadithRuling | None = await session.scalar(
        select(HadithRuling)
        .where(HadithRuling.hadith_id == hadith_id)
        .order_by(HadithRuling.recorded_at.desc(), HadithRuling.id.desc())
        .limit(1)
    )
    return result


async def is_eligible(session: AsyncSession, hadith_id: int) -> bool:
    """Return whether the hadith may be shown as evidence: its latest ruling is صحيح or حسن."""
    ruling = await latest_ruling(session, hadith_id)
    return classification_is_eligible(ruling.classification if ruling else None)


async def enqueue_demand(session: AsyncSession, hadith_id: int) -> bool:
    """
    Count one more request for a hadith that has no ruling yet.

    Return False, and queue nothing, when the hadith already has a ruling.
    """
    if await latest_ruling(session, hadith_id) is not None:
        return False
    statement = pg_insert(HadithVerificationQueue).values(hadith_id=hadith_id, demand_count=1)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[HadithVerificationQueue.hadith_id],
            set_={
                "demand_count": HadithVerificationQueue.demand_count + 1,
                "last_requested_at": func.now(),
            },
        )
    )
    return True


async def record_ruling(session: AsyncSession, hadith_id: int, ruling: RulingInput) -> HadithRuling:
    """Append an editor's ruling to a hadith's history and take the hadith off the queue."""
    if await session.get(Hadith, hadith_id) is None:
        message = f"no stored hadith has id {hadith_id}"
        raise RulingError(message)
    row = HadithRuling(hadith_id=hadith_id, **ruling.model_dump())
    session.add(row)
    await session.execute(
        delete(HadithVerificationQueue).where(HadithVerificationQueue.hadith_id == hadith_id)
    )
    await session.flush()
    return row


async def find_hadith(session: AsyncSession, collection: str, number: str) -> Hadith | None:
    result: Hadith | None = await session.scalar(
        select(Hadith).where(Hadith.collection == collection, Hadith.number == number)
    )
    return result


async def verification_queue(session: AsyncSession, limit: int = 20) -> list[QueuedHadith]:
    """Return the hadiths waiting for a ruling, most wanted first."""
    rows = await session.execute(
        select(
            Hadith,
            HadithVerificationQueue.demand_count,
            HadithVerificationQueue.first_requested_at,
            HadithVerificationQueue.last_requested_at,
        )
        .join(HadithVerificationQueue, HadithVerificationQueue.hadith_id == Hadith.id)
        .order_by(
            HadithVerificationQueue.demand_count.desc(),
            HadithVerificationQueue.first_requested_at,
            Hadith.id,
        )
        .limit(limit)
    )
    return [QueuedHadith(*row) for row in rows]
