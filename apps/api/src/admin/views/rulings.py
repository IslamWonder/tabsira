"""
The rulings queue (decision 18): hadiths waiting for a dorar.net ruling, and the rulings recorded.

dorar.net blocks automated access and is never called from here. The queue page lists the
hadiths the pipeline wanted that have no ruling yet, most wanted first, each with the
dorar search link the editor opens in their own browser. The hadith page shows the stored
text byte for byte, with its hash and source, and a form; recording goes through the same
`record_ruling` and `RulingInput` as the command line, so the dorar-only address check and
the blank-field checks are one piece of code. A ruling is appended, never edited: the
history view below is read-only, and the registry refuses an edit or delete form on it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from pydantic import ValidationError
from sqladmin import BaseView, expose
from sqladmin.filters import StaticValuesFilter
from sqlalchemy import select
from starlette import status
from starlette.datastructures import URL
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from src.admin.audit import client_of
from src.admin.base import ReadOnlyView, current_admin, current_user, labelled
from src.models.admin_audit import AuditAction
from src.models.scripture import (
    Hadith,
    HadithClassification,
    HadithRuling,
    HadithVerificationQueue,
)
from src.scripture.links import dorar_search_url
from src.scripture.rulings import (
    QueuedHadith,
    RulingInput,
    is_eligible,
    is_enriched,
    record_ruling,
    verification_queue,
)
from src.services import admin_audit_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.admin.app import TabsiraAdmin

CATEGORY = "Scripture"
CATEGORY_ICON = "fa-solid fa-book-open"
IDENTITY = "rulings-queue"
# The audit name of a recorded ruling: the identity sqladmin gives the history view below.
RULING_MODEL = "hadith-ruling"
QUEUE_TEMPLATE = "admin/rulings_queue.html"
HADITH_TEMPLATE = "admin/ruling_hadith.html"
# How many waiting hadiths one page shows; the most wanted come first, so the rest can wait.
QUEUE_LIMIT = 200
# What the editor types, in the order of the form; the hadith is fixed by the page.
FORM_FIELDS = (
    "ruling_text",
    "scholar",
    "source_book",
    "page",
    "dorar_url",
    "classification",
    "editor_name",
)
REFUSED = "The ruling was not recorded. Check: {fields}."
NO_HADITH = "No stored hadith has this id."
# The audit reason of a form that was refused; the row names the fields to check.
REFUSED_REASON = "refused"
# An id the database could hold; anything else names no row and is not even looked up.
MAX_ID = 2**63 - 1
# The longest `recorded` query value read back: an id, in ASCII digits.
RECORDED_MAX_DIGITS = 18


@dataclass(frozen=True)
class QueueRow:
    """One waiting hadith as the queue page shows it: its reference and hash, never its text."""

    hadith: Hadith
    demand_count: int
    first_requested_at: Any
    last_requested_at: Any
    dorar_search: str


def _rows(waiting: list[QueuedHadith]) -> list[QueueRow]:
    return [
        QueueRow(
            hadith=item.hadith,
            demand_count=item.demand_count,
            first_requested_at=item.first_requested_at,
            last_requested_at=item.last_requested_at,
            dorar_search=dorar_search_url(item.hadith.text),
        )
        for item in waiting
    ]


def _submitted(form: Any) -> dict[str, str]:
    """
    Return the form's fields as typed, without the token; a missing field is empty.

    A browser sends a text area's line breaks as CRLF whatever the editor typed; the
    command line stores LF. The CR is the form encoding's, not the editor's, and is dropped.
    """
    return {name: str(form.get(name) or "").replace("\r\n", "\n") for name in FORM_FIELDS}


def _refused_names(error: ValidationError) -> list[str]:
    return sorted({str(item["loc"][0]) for item in error.errors() if item["loc"]})


def _hadith_id(request: Request) -> int | None:
    """Return the hadith id of the address, or None when no row could have it."""
    hadith_id = int(request.path_params["hadith_id"])
    return hadith_id if 0 < hadith_id <= MAX_ID else None


def _recorded_id(request: Request) -> int | None:
    """Return the id of the ruling the address says was just recorded, if it reads as one."""
    value = request.query_params.get("recorded", "")
    if value.isascii() and value.isdigit() and len(value) <= RECORDED_MAX_DIGITS:
        return int(value)
    return None


def _refused_fields(names: list[str]) -> str:
    return ", ".join(name.replace("_", " ") for name in names) or "the form"


class RulingsQueueView(BaseView):
    """The queue of hadiths waiting for a ruling, and the page where one is recorded."""

    name = "Rulings queue"
    icon = "fa-solid fa-scale-balanced"
    category = CATEGORY
    category_icon = CATEGORY_ICON

    @property
    def admin(self) -> TabsiraAdmin:
        return cast("TabsiraAdmin", self._admin_ref)

    def _queue_url(self, request: Request, recorded: int | None = None) -> URL:
        url: URL = request.url_for(f"admin:view-{IDENTITY}")
        if recorded is not None:
            url = url.include_query_params(recorded=recorded)
        return url

    async def _hadith_page(
        self,
        request: Request,
        db: AsyncSession,
        hadith: Hadith,
        *,
        values: dict[str, str] | None = None,
        error: str | None = None,
        status_code: int = 200,
    ) -> Response:
        """Render a hadith with its history and the ruling form, filled with `values` if any."""
        history = (
            await db.scalars(
                select(HadithRuling)
                .where(HadithRuling.hadith_id == hadith.id)
                .order_by(HadithRuling.recorded_at.desc(), HadithRuling.id.desc())
            )
        ).all()
        queued = await db.get(HadithVerificationQueue, hadith.id)
        if values is None:
            values = dict.fromkeys(FORM_FIELDS, "")
            values["editor_name"] = current_user(request).display_name or ""
        context: dict[str, Any] = {
            "title": f"{hadith.collection} {hadith.number}",
            "subtitle": self.name,
            "hadith": hadith,
            "dorar_search": dorar_search_url(hadith.text),
            "queued": queued,
            "history": history,
            # The pipeline's own answer, so this page and an insight never disagree.
            "eligible": await is_eligible(db, hadith.id),
            # Decision 58: shown before any ruling, as one of the enriched Sunnah file's hadiths.
            "enriched": await is_enriched(db, hadith.id),
            "classifications": list(HadithClassification),
            "values": values,
            "error": error,
            "queue_url": self._queue_url(request),
        }
        return await self.templates.TemplateResponse(
            request, HADITH_TEMPLATE, context, status_code=status_code
        )

    async def _not_found(self, request: Request) -> Response:
        context = {"title": self.name, "subtitle": NO_HADITH, "missing": True}
        return await self.templates.TemplateResponse(
            request, HADITH_TEMPLATE, context, status_code=status.HTTP_404_NOT_FOUND
        )

    # First on purpose: sqladmin names the view after the route exposed first in the class,
    # and the sidebar links to that name.
    @expose("/rulings-queue", methods=["GET"], identity=IDENTITY)
    async def queue(self, request: Request) -> Response:
        await self.admin.trail.write(
            request, AuditAction.LIST, admin_user_id=current_admin(request), model=IDENTITY
        )
        recorded_id = _recorded_id(request)
        async with self.admin.db() as db:
            waiting = await verification_queue(db, QUEUE_LIMIT)
            # The banner names a ruling that exists; a crafted address shows nothing.
            recorded = None if recorded_id is None else await db.get(HadithRuling, recorded_id)
        context: dict[str, Any] = {
            "title": self.name,
            "subtitle": "Hadiths the engine wanted that have no ruling yet, most wanted first.",
            "rows": _rows(waiting),
            "limit": QUEUE_LIMIT,
            "recorded": recorded,
        }
        return await self.templates.TemplateResponse(request, QUEUE_TEMPLATE, context)

    @expose("/rulings-queue/hadith/{hadith_id:int}", methods=["GET"], identity=f"{IDENTITY}-hadith")
    async def hadith(self, request: Request) -> Response:
        hadith_id = _hadith_id(request)
        if hadith_id is None:
            return await self._not_found(request)
        await self.admin.trail.write(
            request,
            AuditAction.VIEW,
            admin_user_id=current_admin(request),
            model=IDENTITY,
            record_id=str(hadith_id),
        )
        async with self.admin.db() as db:
            hadith = await db.get(Hadith, hadith_id)
            if hadith is None:
                return await self._not_found(request)
            return await self._hadith_page(request, db, hadith)

    @expose(
        "/rulings-queue/hadith/{hadith_id:int}/record",
        methods=["POST"],
        identity=f"{IDENTITY}-record",
    )
    async def record(self, request: Request) -> Response:
        """
        Record the editor's ruling; the audit row names the fields, never what they hold.

        The ruling and its audit row are one transaction: neither exists without the other.
        A refused form is an event too, and gets a row that names the fields to check.
        """
        hadith_id = _hadith_id(request)
        if hadith_id is None:
            return await self._not_found(request)
        admin_id: uuid.UUID = current_admin(request)
        values = _submitted(await request.form())
        ip_hash, user_agent = client_of(self.admin.settings, request)
        async with self.admin.db() as db:
            hadith = await db.get(Hadith, hadith_id)
            if hadith is None:
                return await self._not_found(request)
            try:
                ruling = RulingInput(**values, recorded_by=admin_id)
            except ValidationError as refused:
                names = _refused_names(refused)
                await self.admin.trail.write(
                    request,
                    AuditAction.CREATE,
                    admin_user_id=admin_id,
                    model=RULING_MODEL,
                    record_id=None,
                    fields=names,
                    reason=REFUSED_REASON,
                )
                error = REFUSED.format(fields=_refused_fields(names))
                return await self._hadith_page(
                    request, db, hadith, values=values, error=error, status_code=400
                )
            row = await record_ruling(db, hadith.id, ruling)
            await admin_audit_service.record(
                db,
                action=AuditAction.CREATE,
                admin_user_id=admin_id,
                model=RULING_MODEL,
                record_id=str(row.id),
                fields=FORM_FIELDS,
                ip_hash=ip_hash,
                user_agent=user_agent,
            )
            await db.commit()
            recorded_id = row.id
        return RedirectResponse(
            self._queue_url(request, recorded_id), status_code=status.HTTP_303_SEE_OTHER
        )


class HadithRulingAdmin(ReadOnlyView, model=HadithRuling):
    """
    Every ruling recorded, newest first: the history behind each hadith's eligibility.

    Read-only on purpose: a ruling is recorded from the queue page above, and the registry
    refuses an edit or delete form on this table (a mistake is corrected by a new ruling).
    """

    name = "Hadith ruling"
    name_plural = "Hadith rulings"
    icon = "fa-solid fa-stamp"
    category = CATEGORY
    category_icon = CATEGORY_ICON

    column_list = [
        HadithRuling.id,
        HadithRuling.hadith_id,
        HadithRuling.classification,
        HadithRuling.scholar,
        HadithRuling.source_book,
        HadithRuling.page,
        HadithRuling.editor_name,
        HadithRuling.recorded_by,
        HadithRuling.recorded_at,
    ]
    column_details_list = [
        HadithRuling.id,
        HadithRuling.hadith_id,
        HadithRuling.classification,
        HadithRuling.ruling_text,
        HadithRuling.scholar,
        HadithRuling.source_book,
        HadithRuling.page,
        HadithRuling.dorar_url,
        HadithRuling.editor_name,
        HadithRuling.recorded_by,
        HadithRuling.recorded_at,
    ]
    column_labels = labelled(column_details_list)
    column_searchable_list = [HadithRuling.scholar, HadithRuling.editor_name]
    column_sortable_list = [HadithRuling.recorded_at, HadithRuling.hadith_id]
    column_default_sort = [(HadithRuling.recorded_at, True)]
    column_filters = [
        StaticValuesFilter(
            HadithRuling.classification,
            [(item.value, item.value) for item in HadithClassification],
            "Classification",
        )
    ]
