"""
The developer panel of v2 §23: one scan's stored trace, read in the admin area.

The web app's `/dev/inspect/{scanId}` (a development-only route) hands over to this page,
because an admin session lives on the admin host and nowhere else; here the sign-in, the
second factor, the host check and the audit log already apply. The page shows what the
workflow kept: the scan's status and outcome, every stage of every run with its time
(`scan_events`), every model call with its provider, model, tokens, cost and latency
(`ai_calls`), the entities of the verified scene, and the insights by their references.

Never the photo, and nothing about the person: the owner, the exact location, the answer
the person typed to a clarification and the box they drew stay out of it. The scripture
is named by reference only; its text is never read here. The `dev_inspector` feature switches
the page off, and production keeps it off.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from sqladmin import BaseView, expose
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from src.admin.base import current_admin
from src.models.admin_audit import AuditAction
from src.models.scan import Insight, Scan
from src.models.timeseries import AiCall, ScanEvent
from src.schemas.public_id import parse_public_id

if TYPE_CHECKING:
    from src.admin.app import TabsiraAdmin

IDENTITY = "inspect"
TEMPLATE = "admin/inspect.html"
NO_SCAN = "No scan has this id."
BAD_ID = "A scan id is a positive decimal number."


@dataclass(frozen=True)
class Entity:
    """A thing the verified scene names; the box is reported as present or not, never drawn."""

    id: str
    label: str
    label_arabic: str
    origin: str
    status: str
    boxed: bool


@dataclass(frozen=True)
class InsightRef:
    """An insight by its references: what it cites, never the cited text."""

    id: int
    run: int
    position: int
    engine: str
    title: str
    relation: str
    quran: str | None
    hadith: str | None
    learning_unit_id: str | None
    published: bool


@dataclass(frozen=True)
class Totals:
    calls: int
    failed: int
    cost_usd: float
    input_tokens: int
    output_tokens: int
    latency_ms: int


def _scan_id(raw: str) -> int | None:
    """Return the id a developer typed as an integer the database can hold, or None."""
    try:
        return parse_public_id(raw.strip())
    except ValueError:
        return None


def entities_of(scene: dict[str, Any] | None) -> list[Entity]:
    """Return the scene's entities as the panel shows them; a scan without a scene has none."""
    if not scene:
        return []
    return [
        Entity(
            id=str(raw.get("id", "")),
            label=str(raw.get("label", "")),
            label_arabic=str(raw.get("label_arabic", "")),
            origin=str(raw.get("origin", "")),
            status=str(raw.get("status", "")),
            boxed=raw.get("bbox") is not None,
        )
        for raw in scene.get("entities") or []
    ]


def reference_of(insight: Insight) -> InsightRef:
    quran = None
    if insight.quran_surah is not None:
        quran = f"{insight.quran_surah}:{insight.quran_ayah}"
    hadith = None
    if insight.hadith_collection is not None:
        hadith = f"{insight.hadith_collection} {insight.hadith_number}"
    return InsightRef(
        id=insight.id,
        run=insight.run,
        position=insight.position,
        engine=insight.engine,
        title=insight.title,
        relation=insight.relation,
        quran=quran,
        hadith=hadith,
        learning_unit_id=insight.learning_unit_id,
        published=insight.published_at is not None,
    )


def totals_of(calls: list[AiCall]) -> Totals:
    return Totals(
        calls=len(calls),
        failed=sum(1 for call in calls if not call.ok),
        cost_usd=sum(call.cost_usd or 0.0 for call in calls),
        input_tokens=sum(call.input_tokens for call in calls),
        output_tokens=sum(call.output_tokens for call in calls),
        latency_ms=sum(call.latency_ms for call in calls),
    )


async def _events_of(db: AsyncSession, scan_id: int) -> list[ScanEvent]:
    rows = await db.scalars(
        select(ScanEvent)
        .where(ScanEvent.scan_id == scan_id)
        .order_by(ScanEvent.run, ScanEvent.at, ScanEvent.id)
    )
    return list(rows)


async def _insights_of(db: AsyncSession, scan_id: int) -> list[Insight]:
    rows = await db.scalars(
        select(Insight).where(Insight.scan_id == scan_id).order_by(Insight.run, Insight.position)
    )
    return list(rows)


async def _calls_of(db: AsyncSession, scan_id: int, insight_ids: list[int]) -> list[AiCall]:
    """Return the scan's own calls and the ones made for its insights afterwards (the chat)."""
    by_scan = AiCall.scan_id == scan_id
    where = or_(by_scan, AiCall.insight_id.in_(insight_ids)) if insight_ids else by_scan
    rows = await db.scalars(select(AiCall).where(where).order_by(AiCall.at, AiCall.id))
    return list(rows)


class ScanInspectorView(BaseView):
    """Where a developer reads one scan's trace: a form for the id, then the panel."""

    name = "Scan inspector"
    icon = "fa-solid fa-magnifying-glass-chart"
    category = "Developer"
    category_icon = "fa-solid fa-code"

    @property
    def admin(self) -> TabsiraAdmin:
        return cast("TabsiraAdmin", self._admin_ref)

    async def _form(
        self, request: Request, *, error: str | None = None, status_code: int = 200
    ) -> Response:
        context: dict[str, Any] = {"title": self.name, "error": error, "scan": None}
        return await self.templates.TemplateResponse(
            request, TEMPLATE, context, status_code=status_code
        )

    # First on purpose: sqladmin names the view after the route exposed first in the class,
    # and the sidebar links to that name.
    @expose("/inspect", methods=["GET"], identity=IDENTITY)
    async def form(self, request: Request) -> Response:
        raw = request.query_params.get("scan_id", "")
        if not raw.strip():
            return await self._form(request)
        scan_id = _scan_id(raw)
        if scan_id is None:
            return await self._form(request, error=BAD_ID, status_code=status.HTTP_400_BAD_REQUEST)
        return RedirectResponse(
            request.url_for(f"admin:view-{IDENTITY}-scan", scan_id=scan_id),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @expose("/inspect/{scan_id:int}", methods=["GET"], identity=f"{IDENTITY}-scan")
    async def scan(self, request: Request) -> Response:
        scan_id = _scan_id(str(request.path_params["scan_id"]))
        if scan_id is None:
            # An id the database could not hold names nothing: not looked up, not audited.
            return await self._form(request, error=NO_SCAN, status_code=status.HTTP_404_NOT_FOUND)
        await self.admin.trail.write(
            request,
            AuditAction.VIEW,
            admin_user_id=current_admin(request),
            model="scan",
            record_id=str(scan_id),
        )
        async with self.admin.db() as db:
            scan = await db.get(Scan, scan_id)
            if scan is None:
                return await self._form(
                    request, error=NO_SCAN, status_code=status.HTTP_404_NOT_FOUND
                )
            insights = await _insights_of(db, scan_id)
            events = await _events_of(db, scan_id)
            calls = await _calls_of(db, scan_id, [insight.id for insight in insights])
        duration_ms = None
        if scan.finished_at is not None:
            duration_ms = round((scan.finished_at - scan.created_at).total_seconds() * 1000)
        scene = scan.scene or {}
        context: dict[str, Any] = {
            "title": f"Scan {scan.id}",
            "subtitle": self.name,
            "scan": scan,
            "duration_ms": duration_ms,
            "description": scene.get("description"),
            "scene_model": scene.get("model"),
            "scene_provider": scene.get("provider"),
            "ambiguities": scene.get("ambiguities") or [],
            "rejected": scene.get("rejected") or [],
            "entities": entities_of(scan.scene),
            "events": events,
            "calls": calls,
            "totals": totals_of(calls),
            "insights": [reference_of(insight) for insight in insights],
            "form_url": request.url_for(f"admin:view-{IDENTITY}"),
        }
        return await self.templates.TemplateResponse(request, TEMPLATE, context)
