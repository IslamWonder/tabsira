"""
Editorial grading from dorar.net (decisions 18 and 58): rulings, eligibility and the verification queue.

dorar.net is never called from the server. An editor opens it in a browser and
records the ruling exactly as dorar gives it, with the scholar, the book and
page, the dorar page address, and the editor's reading of it as one of five
classifications. Rulings are only ever added (the database refuses to change
or remove one); the latest is the one in force.

Eligibility as evidence (decision 64, which abrogates decisions 18 and 58): a
hadith with no ruling is shown as it is; a hadith an editor explicitly ruled out
(ضعيف, موضوع, مختلف فيه) is not, so a recorded judgement is never contradicted. No
ruling is displayed anywhere for now. The queue still counts which unruled hadiths
the engine shows, for the better way of showing a ruling the owners will choose
later; nothing waits for it. The enriched-file helpers stay for the admin area.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, field_validator
from sqlalchemy import delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    Hadith,
    HadithClassification,
    HadithRuling,
    HadithSignal,
    HadithVerificationQueue,
)
from src.scripture.errors import ScriptureError

ELIGIBLE = frozenset({HadithClassification.SAHIH, HadithClassification.HASAN})
# Decision 58: the share of a record's word runs the hadith must hold for the link to count.
ENRICHED_MIN_COVERAGE = 0.8
# The dataset grades that call a narration weak: the English transliterations of the
# imported books (docs/ASSET_MANIFEST.md §3: ضعيف in every spelling, منكر, موضوع, باطل, شاذ,
# معلول, مرسل), the other usual spellings, and the Arabic words a later import may carry.
WEAK_GRADE = re.compile(
    r"da['\u02bf\u2019]?e?if|dhaif|munkar|maw?du|maudu|batil|shaa?dh|malool|ma['\u02bf\u2019]?lul"
    r"|mursal"
    r"|matr[ou]+k|munqati|mudtarib"
    r"|ضعيف|منكر|موضوع|باطل|شاذ|معلول|مرسل|متروك|منقطع|مضطرب",
    re.IGNORECASE,
)
# Written out again as the check constraint of `hadith_rulings.dorar_url`; a test keeps them equal.
DORAR_PAGE = re.compile(r"https://(www\.)?dorar\.net/\S+")


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
        if "\x00" in value:
            message = "must not hold a NUL character"
            raise ValueError(message)
        return value

    @field_validator("dorar_url")
    @classmethod
    def _on_dorar(cls, value: str) -> str:
        # The same rule as the table's check constraint, so what passes here is stored: an
        # address the parser would accept but the database refuse (a port, a user part, an
        # upper-case host) is refused here first.
        if DORAR_PAGE.fullmatch(value) is None:
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


def eligible_given(ruling: HadithRuling | None) -> bool:
    """
    Decide eligibility from what is already read.

    The ruling in force, when there is one, decides alone; without one the hadith is shown
    as it is (decision 64).
    """
    if ruling is not None:
        return classification_is_eligible(ruling.classification)
    return True


def weak_by_dataset(grades: Iterable[Mapping[str, str]] | None) -> bool:
    """Tell whether any grader of the dataset calls the narration weak."""
    return any(WEAK_GRADE.search(str(grade.get("grade", ""))) for grade in grades or ())


async def enriched_among(session: AsyncSession, hadith_ids: Iterable[int]) -> set[int]:
    """
    Return which of these hadiths count as the enriched Sunnah file's (decision 58), in one query.

    A record's link counts only as its best match (`hadith_id`), at ENRICHED_MIN_COVERAGE or
    more, into a book the record cites (the import marks that match `cited`); a hadith any
    dataset grader calls weak does not count, whatever links to it.
    """
    wanted = sorted(set(hadith_ids))
    if not wanted:
        return set()
    strong_link = exists().where(
        HadithSignal.hadith_id == Hadith.id,
        HadithSignal.match_coverage >= ENRICHED_MIN_COVERAGE,
        HadithSignal.matches[0]["cited"].as_boolean().is_(True),
    )
    rows = await session.execute(
        select(Hadith.id, Hadith.informational_grades).where(Hadith.id.in_(wanted), strong_link)
    )
    return {row.id for row in rows if not weak_by_dataset(row.informational_grades)}


async def is_enriched(session: AsyncSession, hadith_id: int) -> bool:
    """Tell whether the hadith counts as one of the enriched Sunnah file's (decision 58)."""
    return hadith_id in await enriched_among(session, [hadith_id])


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
    """Return whether the hadith may be shown: no ruling, or a ruling of صحيح or حسن (decision 64)."""
    return eligible_given(await latest_ruling(session, hadith_id))


async def enqueue_demand(session: AsyncSession, hadith_id: int) -> bool:
    """
    Count one more showing of a hadith that has no ruling yet.

    Nothing waits for the ruling (decision 64): the count only tells the editors which
    hadiths are shown most. Return False, and queue nothing, when the hadith already has
    a ruling.
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
