"""
The moderation queue: held and reported posts and comments, decided one at a time.

A moderator opens an item, reads it and its reports, and decides: approve (publish a held or
refused item, or restore a removed one), reject a held one, or remove a published one. A
rejection or a removal carries a reason the author is shown, chosen from the codes the app
defines (`src/messages.py`): the moderator's own words never reach the author. Every decision
goes through `moderation_service`, which writes the moderation log and closes the item's open
reports; the admin audit log gets a row with the item's id and the decision's name, never the
text. The reports and the moderation log have read-only views of their own.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from sqladmin import BaseView, expose
from sqladmin.filters import StaticValuesFilter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from starlette.datastructures import URL
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from src.admin.base import ReadOnlyView, current_admin, labelled
from src.errors import AppError
from src.messages import messages_for
from src.models.admin_audit import AuditAction
from src.models.moderation import (
    ModerationAction,
    ModerationActionKind,
    ModerationSource,
    ModerationTarget,
)
from src.models.social import (
    Comment,
    InsightPublication,
    Post,
    PostStatus,
    Report,
    ReportReason,
    ReportStatus,
    ReportTarget,
)
from src.services import moderation_service

if TYPE_CHECKING:
    from src.admin.app import TabsiraAdmin

CATEGORY = "Social"
CATEGORY_ICON = "fa-solid fa-comments"
IDENTITY = "moderation-queue"
QUEUE_TEMPLATE = "admin/moderation_queue.html"
ITEM_TEMPLATE = "admin/moderation_item.html"
# How many held or reported items of each kind one page shows, oldest first.
QUEUE_LIMIT = 200
KINDS: dict[str, type[Post] | type[Comment]] = {
    ReportTarget.POST.value: Post,
    ReportTarget.COMMENT.value: Comment,
}
DECISIONS = ("approve", "reject", "remove")
NO_ITEM = "No post or comment has this id."
UNKNOWN_REASON = "Choose a reason from the list: the author is shown its text, never yours."
STALE = "This decision does not apply to the item as it is now; it was reloaded."

type Item = Post | Comment


@dataclass(frozen=True)
class QueueRow:
    """One held or reported item as the queue page lists it."""

    kind: str
    item: Item
    open_reports: int
    created_at: datetime


def _record_id(kind: str, item_id: int) -> str:
    """Return the audit log's name for an item: its kind and its id, `post:123`."""
    return f"{kind}:{item_id}"


def reason_choices() -> list[tuple[str, str]]:
    """Return the reason codes a moderator may give, with the Arabic label the author reads."""
    return sorted(messages_for().reason_labels.items())


def _open_reports(kind: str) -> Any:
    """Return a subquery counting the open reports of each item of `kind`."""
    return (
        select(Report.target_id, func.count().label("open_reports"))
        .where(Report.target_type == ReportTarget(kind), Report.status == ReportStatus.OPEN)
        .group_by(Report.target_id)
        .subquery()
    )


async def _queue_of(db: AsyncSession, kind: str) -> list[QueueRow]:
    """Return the items of `kind` to look at: held ones, and published ones with open reports."""
    model = KINDS[kind]
    reports = _open_reports(kind)
    rows = await db.execute(
        select(model, func.coalesce(reports.c.open_reports, 0))
        .outerjoin(reports, reports.c.target_id == model.id)
        .where(
            (model.status == PostStatus.PENDING_REVIEW.value)
            | ((model.status == PostStatus.PUBLISHED.value) & (reports.c.open_reports > 0))
        )
        .order_by(model.created_at, model.id)
        .limit(QUEUE_LIMIT)
    )
    return [QueueRow(kind, item, int(count), item.created_at) for item, count in rows]


async def _reports_of(db: AsyncSession, kind: str, item_id: int) -> list[Report]:
    return list(
        (
            await db.scalars(
                select(Report)
                .where(Report.target_type == ReportTarget(kind), Report.target_id == item_id)
                .order_by(Report.status, Report.created_at)
            )
        ).all()
    )


async def _log_of(db: AsyncSession, kind: str, item_id: int) -> list[ModerationAction]:
    return list(
        (
            await db.scalars(
                select(ModerationAction)
                .where(
                    ModerationAction.target_type == ModerationTarget(kind),
                    ModerationAction.target_id == item_id,
                )
                .order_by(ModerationAction.at.desc(), ModerationAction.id.desc())
            )
        ).all()
    )


class ModerationQueueView(BaseView):
    """The queue of held and reported items, and the page where one is decided."""

    name = "Moderation queue"
    icon = "fa-solid fa-gavel"
    category = CATEGORY
    category_icon = CATEGORY_ICON

    @property
    def admin(self) -> TabsiraAdmin:
        return cast("TabsiraAdmin", self._admin_ref)

    def _queue_url(self, request: Request, decided: str | None = None) -> URL:
        url: URL = request.url_for(f"admin:view-{IDENTITY}")
        if decided is not None:
            url = url.include_query_params(decided=decided)
        return url

    # First on purpose: sqladmin names the view after the route exposed first in the class,
    # and the sidebar links to that name.
    @expose("/moderation-queue", methods=["GET"], identity=IDENTITY)
    async def queue(self, request: Request) -> Response:
        await self.admin.trail.write(
            request, AuditAction.LIST, admin_user_id=current_admin(request), model=IDENTITY
        )
        async with self.admin.db() as db:
            posts = await _queue_of(db, ReportTarget.POST.value)
            comments = await _queue_of(db, ReportTarget.COMMENT.value)
        context: dict[str, Any] = {
            "title": self.name,
            "subtitle": "Posts and comments held for a person, and published ones with open reports.",
            "posts": posts,
            "comments": comments,
            "limit": QUEUE_LIMIT,
            "decided": request.query_params.get("decided"),
        }
        return await self.templates.TemplateResponse(request, QUEUE_TEMPLATE, context)

    async def _item_page(
        self,
        request: Request,
        db: AsyncSession,
        kind: str,
        item: Item,
        *,
        error: str | None = None,
        status_code: int = 200,
    ) -> Response:
        """Render an item with its text, its reports, its log, and the decisions that fit it."""
        publication = None
        if isinstance(item, Post) and item.publication_id is not None:
            publication = await db.get(InsightPublication, item.publication_id)
        context: dict[str, Any] = {
            "title": f"{kind.capitalize()} {item.id}",
            "subtitle": self.name,
            "kind": kind,
            "item": item,
            "text": item.reflection if isinstance(item, Post) else item.body,
            "publication": publication,
            "reports": await _reports_of(db, kind, item.id),
            "log": await _log_of(db, kind, item.id),
            "reasons": reason_choices(),
            "can_reject": item.status == PostStatus.PENDING_REVIEW.value,
            "can_remove": item.status == PostStatus.PUBLISHED.value,
            "can_approve": item.status != PostStatus.PUBLISHED.value
            and not (isinstance(item, Post) and item.status == PostStatus.DRAFT.value),
            "error": error,
            "queue_url": self._queue_url(request),
        }
        return await self.templates.TemplateResponse(
            request, ITEM_TEMPLATE, context, status_code=status_code
        )

    async def _not_found(self, request: Request) -> Response:
        context = {"title": self.name, "subtitle": NO_ITEM, "missing": True}
        return await self.templates.TemplateResponse(
            request, ITEM_TEMPLATE, context, status_code=status.HTTP_404_NOT_FOUND
        )

    async def _load(self, db: AsyncSession, request: Request) -> tuple[str, Item | None]:
        kind = str(request.path_params["kind"])
        model = KINDS.get(kind)
        if model is None:
            return kind, None
        item: Item | None = await db.get(model, int(request.path_params["item_id"]))
        return kind, item

    @expose("/moderation-queue/{kind}/{item_id:int}", methods=["GET"], identity=f"{IDENTITY}-item")
    async def item(self, request: Request) -> Response:
        await self.admin.trail.write(
            request,
            AuditAction.VIEW,
            admin_user_id=current_admin(request),
            model=IDENTITY,
            record_id=_record_id(
                str(request.path_params["kind"]), int(request.path_params["item_id"])
            ),
        )
        async with self.admin.db() as db:
            kind, item = await self._load(db, request)
            if item is None:
                return await self._not_found(request)
            return await self._item_page(request, db, kind, item)

    @expose(
        "/moderation-queue/{kind}/{item_id:int}/{decision}",
        methods=["POST"],
        identity=f"{IDENTITY}-decide",
    )
    async def decide(self, request: Request) -> Response:
        """Apply one decision through the moderation service; the audit row names it."""
        decision = str(request.path_params["decision"])
        admin_id: uuid.UUID = current_admin(request)
        reason = moderation_service.known_reason(str((await request.form()).get("reason") or ""))
        async with self.admin.db() as db:
            kind, item = await self._load(db, request)
            if item is None or decision not in DECISIONS:
                return await self._not_found(request)
            if decision != "approve" and reason is None:
                return await self._item_page(
                    request, db, kind, item, error=UNKNOWN_REASON, status_code=400
                )
            try:
                if decision == "approve":
                    await moderation_service.approve(db, item, admin_id)
                elif decision == "reject":
                    await moderation_service.reject(db, item, admin_id, cast("str", reason))
                else:
                    await moderation_service.remove(db, item, admin_id, cast("str", reason))
            except AppError:
                # The service read the item fresh and changed nothing: show it as it is now.
                return await self._item_page(
                    request, db, kind, item, error=STALE, status_code=status.HTTP_409_CONFLICT
                )
            await db.commit()
            record_id = _record_id(kind, item.id)
        await self.admin.trail.write(
            request,
            AuditAction.UPDATE,
            admin_user_id=admin_id,
            model=IDENTITY,
            record_id=record_id,
            reason=decision,
        )
        return RedirectResponse(
            self._queue_url(request, record_id), status_code=status.HTTP_303_SEE_OTHER
        )


class ReportAdmin(ReadOnlyView, model=Report):
    """Every report filed, open ones first; a report is closed by a decision, never here."""

    name = "Report"
    name_plural = "Reports"
    icon = "fa-solid fa-flag"
    category = CATEGORY
    category_icon = CATEGORY_ICON

    column_list = [
        Report.id,
        Report.target_type,
        Report.target_id,
        Report.reason,
        Report.status,
        Report.reporter_id,
        Report.created_at,
        Report.handled_at,
        Report.handled_by,
    ]
    column_details_list = [*column_list, Report.details]
    column_labels = labelled(column_details_list)
    column_sortable_list = [Report.created_at, Report.status, Report.target_id]
    column_default_sort = [(Report.status, True), (Report.created_at, False)]
    column_filters = [
        StaticValuesFilter(
            Report.status, [(item.value, item.value) for item in ReportStatus], "Status"
        ),
        StaticValuesFilter(
            Report.reason, [(item.value, item.value) for item in ReportReason], "Reason"
        ),
        StaticValuesFilter(
            Report.target_type, [(item.value, item.value) for item in ReportTarget], "Target"
        ),
    ]


class ModerationActionAdmin(ReadOnlyView, model=ModerationAction):
    """The moderation log, newest first: append-only, like the audit log."""

    name = "Moderation log"
    name_plural = "Moderation log"
    icon = "fa-solid fa-clipboard-check"
    category = CATEGORY
    category_icon = CATEGORY_ICON

    column_list = [
        ModerationAction.at,
        ModerationAction.target_type,
        ModerationAction.target_id,
        ModerationAction.action,
        ModerationAction.source,
        ModerationAction.actor_id,
        ModerationAction.reason,
        ModerationAction.details,
    ]
    column_labels = labelled(column_list)
    # The key is (at, id): there is no record page, and the list shows everything.
    can_view_details = False
    column_details_list = column_list
    column_sortable_list = [ModerationAction.at, ModerationAction.action]
    column_default_sort = [(ModerationAction.at, True)]
    column_filters = [
        StaticValuesFilter(
            ModerationAction.action,
            [(item.value, item.value) for item in ModerationActionKind],
            "Action",
        ),
        StaticValuesFilter(
            ModerationAction.source,
            [(item.value, item.value) for item in ModerationSource],
            "Source",
        ),
    ]
