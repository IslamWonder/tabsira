"""
What the admin area writes to the audit log, and when.

`AuditTrail` writes a row from a request: it opens its own session and commits, so the
row survives a request that goes on to fail. Three things feed it:

- the authentication backend, for sign-in, failed sign-in and sign-out;
- `AdminAuth.authenticate`, which records every list page, every record page and every
  bulk action as the request arrives (an attempt is an event even when it is refused);
- sqladmin's audit hook, `AdminAuditBackend`, for create, update and delete, after the
  change is committed.

Only names reach the log: the changed fields come from `request.state` (set by
`AdminView.on_model_change`) or, failing that, from the submitted form's keys; the values
of the form are never read here.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable

from sqladmin.audit import AuditBackend, AuditEntry
from sqladmin.authentication import get_current_user_id
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import Request

from src.config import Settings
from src.models.admin_audit import AuditAction
from src.services import admin_audit_service, auth_service

# The attribute of `request.state` that holds the names of the fields that changed.
CHANGED_FIELDS_ATTR = "admin_changed_fields"
# What an admin request's path says it does, relative to the admin's own base URL.
_ACCESS = re.compile(r"^/(?P<identity>[^/]+)/(?P<kind>list|details|action)(?:/(?P<rest>.+))?$")


def _reason_of(slug: str) -> str | None:
    """Return an action's slug as a reason code; what the address holds is not trusted."""
    code = re.sub(r"[^a-z0-9_]", "", slug.lower().replace("-", "_"))[:64]
    return code or None


def relative_path(request: Request) -> str:
    """Return the request's path below the admin's base URL, as the admin's router sees it."""
    path: str = request.scope["path"]
    root: str = request.scope.get("root_path", "")
    return path[len(root) :] if root and path.startswith(root + "/") else path


def client_of(settings: Settings, request: Request) -> tuple[str, str | None]:
    """Return the keyed hash of the caller's address and its user agent."""
    host = request.client.host if request.client else None
    return auth_service.hash_ip(settings, host), request.headers.get("user-agent")


class AuditTrail:
    """Writes audit rows for requests of the admin area."""

    def __init__(self, settings: Settings, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self.settings = settings
        self.session_maker = session_maker

    async def write(
        self,
        request: Request,
        action: AuditAction,
        *,
        admin_user_id: uuid.UUID | None,
        model: str | None = None,
        record_id: str | None = None,
        fields: Iterable[str] = (),
        reason: str | None = None,
        ids: Iterable[str] = (),
    ) -> None:
        """Add one row for `request` and commit it."""
        ip_hash, user_agent = client_of(self.settings, request)
        async with self.session_maker() as db:
            await admin_audit_service.record(
                db,
                action=action,
                admin_user_id=admin_user_id,
                model=model,
                record_id=record_id,
                fields=fields,
                reason=reason,
                ids=ids,
                ip_hash=ip_hash,
                user_agent=user_agent,
            )
            await db.commit()

    async def access(self, request: Request, admin_user_id: uuid.UUID) -> None:
        """Record a list page, a record page or a bulk action, if that is what `request` is."""
        match = _ACCESS.match(relative_path(request))
        if match is None:
            return
        identity, kind, rest = match["identity"], match["kind"], match["rest"]
        if kind == "list" and rest is None and request.method == "GET":
            await self.write(request, AuditAction.LIST, admin_user_id=admin_user_id, model=identity)
        elif kind == "details" and rest is not None and request.method == "GET":
            await self.write(
                request,
                AuditAction.VIEW,
                admin_user_id=admin_user_id,
                model=identity,
                record_id=rest,
            )
        elif kind == "action" and rest is not None and request.method == "POST":
            pks = request.query_params.get("pks", "")
            await self.write(
                request,
                AuditAction.BULK_ACTION,
                admin_user_id=admin_user_id,
                model=identity,
                reason=_reason_of(rest),
                ids=[pk for pk in pks.split(",") if pk],
            )


class AdminAuditBackend(AuditBackend):
    """sqladmin's hook for create, update and delete: writes the names of the changed fields."""

    def __init__(self, trail: AuditTrail) -> None:
        self.trail = trail

    async def log(self, entry: AuditEntry, request: Request) -> None:
        actor = get_current_user_id(request)
        fields = getattr(request.state, CHANGED_FIELDS_ATTR, None)
        if fields is None:
            fields = list(entry.changes or ())
        # sqladmin treats a failing hook as best effort and only logs it, which would lose the
        # row: a name that is not a column name is left out rather than refused.
        fields = [name for name in fields if admin_audit_service.is_field_name(name)]
        await self.trail.write(
            request,
            AuditAction(entry.action),
            admin_user_id=uuid.UUID(str(actor)) if actor else None,
            model=entry.identity,
            record_id=entry.pk,
            fields=fields,
        )
