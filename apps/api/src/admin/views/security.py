"""Security in the admin area: the audit log, and the page where an admin enrols the second factor."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from sqladmin import BaseView, expose
from sqladmin.filters import StaticValuesFilter
from starlette import status
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from src.admin.audit import client_of
from src.admin.base import ReadOnlyView, current_user, labelled
from src.errors import AppError
from src.models.admin_audit import AdminAuditLog, AuditAction
from src.models.login_attempt import AttemptKind
from src.services import admin_totp_service, auth_service, rate_limit

if TYPE_CHECKING:
    from src.admin.app import TabsiraAdmin

CATEGORY = "Security"
CATEGORY_ICON = "fa-solid fa-shield-halved"
TWO_FACTOR_TEMPLATE = "admin/two_factor.html"
WRONG_CODE = "That code is wrong."
TOO_MANY = "Too many attempts. Try again later."
NOT_STARTED = "Start the enrolment first."
ALREADY_ON = "Two-factor sign-in is already on. Switch it off first to enrol again."


class AdminAuditLogAdmin(ReadOnlyView, model=AdminAuditLog):
    """
    The audit log, newest first.

    Nothing here can be changed or deleted, by the admin area or by the database: a
    trigger refuses it, and rows leave only with the retention policy.
    """

    name = "Audit log"
    name_plural = "Audit log"
    icon = "fa-solid fa-clipboard-list"
    category = CATEGORY
    category_icon = CATEGORY_ICON

    column_list = [
        AdminAuditLog.at,
        AdminAuditLog.admin_user_id,
        AdminAuditLog.action,
        AdminAuditLog.model,
        AdminAuditLog.record_id,
        AdminAuditLog.details,
        AdminAuditLog.ip_hash,
        AdminAuditLog.user_agent,
    ]
    column_labels = labelled(column_list)
    # The key is (at, id): there is no record page, and the list shows everything.
    can_view_details = False
    column_details_list = column_list
    column_sortable_list = [AdminAuditLog.at, AdminAuditLog.action, AdminAuditLog.model]
    column_default_sort = [(AdminAuditLog.at, True)]
    column_searchable_list = [AdminAuditLog.model, AdminAuditLog.record_id]
    column_filters = [
        StaticValuesFilter(
            AdminAuditLog.action, [(item.value, item.value) for item in AuditAction], "Action"
        )
    ]


class TwoFactorView(BaseView):
    """
    Where an admin turns the second factor on and off for their own account.

    Enrolling takes two steps, so an authenticator that did not take the secret never
    locks anyone out: start (a secret is shown to type into the app), then confirm with
    the first code, which also shows the recovery codes once. Switching it off asks for a
    current code, or a recovery code.
    """

    name = "Two-factor sign-in"
    icon = "fa-solid fa-mobile-screen"
    category = CATEGORY
    category_icon = CATEGORY_ICON

    @property
    def admin(self) -> TabsiraAdmin:
        return cast("TabsiraAdmin", self._admin_ref)

    async def _page(
        self,
        request: Request,
        *,
        error: str | None = None,
        status_code: int = 200,
        recovery_codes: list[str] | None = None,
    ) -> Response:
        """Render the page for the admin's current state: off, started, or on."""
        user = current_user(request)
        async with self.admin.db() as db:
            row = await admin_totp_service.get(db, user.id)
        secret = None
        if row is not None and row.enabled_at is None:
            secret = admin_totp_service.decrypt_secret(self.admin.settings, row.secret_encrypted)
        context: dict[str, Any] = {
            "title": self.name,
            "error": error,
            "enabled": admin_totp_service.is_enabled(row),
            "enabled_at": row.enabled_at if row else None,
            "codes_left": len(row.recovery_hashes) if row else 0,
            "secret": None if secret is None else admin_totp_service.readable(secret),
            "uri": None if secret is None else admin_totp_service.provisioning_uri(user, secret),
            "recovery_codes": recovery_codes,
            "required": self.admin.settings.admin_require_two_factor,
        }
        return await self.templates.TemplateResponse(
            request, TWO_FACTOR_TEMPLATE, context, status_code=status_code
        )

    def _to_page(self, request: Request) -> Response:
        return RedirectResponse(
            request.url_for("admin:view-two-factor"), status_code=status.HTTP_303_SEE_OTHER
        )

    @expose("/two-factor", methods=["GET"], identity="two-factor")
    async def show(self, request: Request) -> Response:
        return await self._page(request)

    @expose("/two-factor/start", methods=["POST"], identity="two-factor-start")
    async def start(self, request: Request) -> Response:
        user = current_user(request)
        async with self.admin.db() as db:
            if admin_totp_service.is_enabled(await admin_totp_service.get(db, user.id)):
                return await self._page(request, error=ALREADY_ON, status_code=400)
            await admin_totp_service.start_enrollment(db, self.admin.settings, user)
            await db.commit()
        return self._to_page(request)

    @expose("/two-factor/confirm", methods=["POST"], identity="two-factor-confirm")
    async def confirm(self, request: Request) -> Response:
        user = current_user(request)
        code = str((await request.form()).get("code") or "").strip()
        async with self.admin.db() as db:
            row = await admin_totp_service.get(db, user.id)
            if row is None or row.enabled_at is not None:
                return await self._page(request, error=NOT_STARTED, status_code=400)
            codes = await admin_totp_service.confirm_enrollment(db, self.admin.settings, user, code)
            if codes is None:
                return await self._page(request, error=WRONG_CODE, status_code=400)
            await db.commit()
        await self.admin.trail.write(request, AuditAction.TWO_FACTOR_ENABLED, admin_user_id=user.id)
        return await self._page(request, recovery_codes=codes)

    @expose("/two-factor/disable", methods=["POST"], identity="two-factor-disable")
    async def disable(self, request: Request) -> Response:
        user = current_user(request)
        code = str((await request.form()).get("code") or "").strip()
        settings = self.admin.settings
        ip_hash, _ = client_of(settings, request)
        email_hash = auth_service.hash_email(settings, user.email)
        async with self.admin.db() as db:
            try:
                attempt = await rate_limit.reserve(
                    db, settings, AttemptKind.LOGIN, ip_hash=ip_hash, email_hash=email_hash
                )
            except AppError:
                return await self._page(request, error=TOO_MANY, status_code=429)
            correct = await admin_totp_service.verify(db, settings, user, code)
            if correct:
                await rate_limit.settle(db, attempt)
                await admin_totp_service.disable(db, user.id)
            await db.commit()
        if not correct:
            return await self._page(request, error=WRONG_CODE, status_code=400)
        await self.admin.trail.write(
            request, AuditAction.TWO_FACTOR_DISABLED, admin_user_id=user.id
        )
        return self._to_page(request)
