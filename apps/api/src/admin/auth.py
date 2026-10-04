"""
Signing in to the admin area, and checking every request after that.

The admin signs in with a real account that has `is_admin`: the e-mail address and
password that the account already has (bcrypt, the same check as `/auth/login`), and,
once the admin has enrolled it, a code from their authenticator app or a recovery code.
What a refusal says never depends on why it was refused: the page always says the
e-mail, the password or the code is wrong, so it cannot be used to learn which accounts
are admins or have a second factor. The real reason goes to the audit log.

Sign-in is rate limited with the accounts limiter (`rate_limit`, kind `login`), per IP
address and per e-mail address, before any password is checked. After sign-in there is
nothing in the cookie but a random token: `authenticate` loads the session on every
request and insists the account is still an active admin, so revoking `is_admin`
(`python -m src.cli.make_admin --revoke`) takes effect on the next request.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from sqladmin.authentication import AuthenticationBackend
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from src import security
from src.admin import csrf
from src.admin.audit import AuditTrail, client_of, relative_path
from src.config import Settings
from src.errors import AppError
from src.models.admin_access import AdminSession
from src.models.admin_audit import AuditAction
from src.models.login_attempt import AttemptKind
from src.models.user import User
from src.services import (
    admin_session_service,
    admin_totp_service,
    auth_service,
    rate_limit,
)

log = logging.getLogger("tabsira.admin.auth")

LOGIN_TEMPLATE = "sqladmin/login.html"
LOGOUT_TEMPLATE = "admin/logout.html"
# The one message a refused sign-in gets, whatever the reason.
REFUSED_MESSAGE = "The e-mail address, the password or the code is wrong."
EXPIRED_MESSAGE = "This page expired. Reload it and try again."
RATE_LIMITED_MESSAGE = "Too many attempts. Try again later."
CSRF_MESSAGE = "The request has no valid CSRF token. Reload the page and try again."
# Under ADMIN_REQUIRE_TWO_FACTOR an admin without the second factor reaches only these.
ENROLMENT_PATHS = ("/two-factor", "/logout", "/statics")


@dataclass(frozen=True, slots=True)
class Context:
    """Who is signed in on this request, and the token their requests must carry."""

    session: AdminSession
    user: User
    token: str
    csrf: str


class AdminAuth(AuthenticationBackend):
    """The admin area's authentication backend, with its own sessions and CSRF tokens."""

    # Set by `TabsiraAdmin` once the admin's templates exist; the backend renders the
    # sign-in page itself, and sqladmin builds its template environment inside `Admin`.
    templates: Any = None

    def __init__(
        self,
        settings: Settings,
        session_maker: async_sessionmaker[AsyncSession],
        trail: AuditTrail,
    ) -> None:
        # No SessionMiddleware: the admin keeps its sessions in `admin_sessions`.
        self.middlewares = []
        self.settings = settings
        self.session_maker = session_maker
        self.trail = trail

    # ─── Sign-in ───────────────────────────────────────────────────

    async def render_login(
        self,
        request: Request,
        *,
        error: str | None = None,
        status_code: int = 200,
        email: str = "",
        headers: dict[str, str] | None = None,
    ) -> Response:
        """Serve the sign-in form with a fresh token, and the cookie that token answers to."""
        nonce = csrf.new_login_nonce()
        response: Response = await self.templates.TemplateResponse(
            request,
            LOGIN_TEMPLATE,
            {
                "error": error,
                "email": email,
                "login_token": csrf.login_form_token(self.settings, nonce),
            },
            status_code=status_code,
        )
        csrf.set_login_cookie(response, nonce)
        for name, value in (headers or {}).items():
            response.headers[name] = value
        return response

    async def login(self, request: Request) -> Response:
        form = await request.form()
        email = str(form.get("email") or "").strip()
        password = str(form.get("password") or "")
        code = str(form.get("code") or "").strip()
        submitted = form.get(csrf.CSRF_FIELD)
        if not csrf.login_form_valid(
            self.settings, request, submitted if isinstance(submitted, str) else None
        ):
            return await self.render_login(
                request, error=EXPIRED_MESSAGE, status_code=403, email=email
            )
        ip_hash, user_agent = client_of(self.settings, request)
        email_hash = auth_service.hash_email(self.settings, email)
        async with self.session_maker() as db:
            try:
                await rate_limit.check(
                    db, self.settings, AttemptKind.LOGIN, ip_hash=ip_hash, email_hash=email_hash
                )
            except AppError as limited:
                await self.trail.write(
                    request, AuditAction.SIGN_IN_FAILED, admin_user_id=None, reason="rate_limited"
                )
                return await self.render_login(
                    request,
                    error=RATE_LIMITED_MESSAGE,
                    status_code=429,
                    email=email,
                    headers=limited.headers,
                )
            user, reason = await self._check(db, email, password, code)
            await rate_limit.record(
                db,
                self.settings,
                AttemptKind.LOGIN,
                ip_hash=ip_hash,
                email_hash=email_hash,
                succeeded=reason is None,
            )
            if user is None or reason is not None:
                await db.commit()
                await self.trail.write(
                    request,
                    AuditAction.SIGN_IN_FAILED,
                    admin_user_id=user.id if user else None,
                    reason=reason,
                )
                return await self.render_login(
                    request, error=REFUSED_MESSAGE, status_code=401, email=email
                )
            return await self._start_session(db, request, user, ip_hash, user_agent)

    async def _check(
        self, db: AsyncSession, email: str, password: str, code: str
    ) -> tuple[User | None, str | None]:
        """
        Check the account, the password and the second factor; return the account and why not.

        The password is checked even when no account has the address, against a decoy,
        so the answer and its timing do not say whether it exists. The code is asked for
        only after the password, and only of an admin who has enrolled.
        """
        user = await auth_service.find_by_email(db, email)
        correct = await asyncio.to_thread(
            security.verify_password,
            password,
            user.password_hash if user else None,
            self.settings.password_bcrypt_rounds,
        )
        if user is None:
            return None, "unknown_account"
        refusal = self._account_refusal(user, correct=correct)
        if refusal is None:
            refusal = await self._second_factor_refusal(db, user, code)
        return user, refusal

    @staticmethod
    def _account_refusal(user: User, *, correct: bool) -> str | None:
        """Return why the account may not sign in to the admin area, or None when it may."""
        checks = (
            (not correct, "bad_password"),
            (not user.is_admin, "not_admin"),
            (not auth_service.can_sign_in(user), "account_disabled"),
        )
        return next((reason for failed, reason in checks if failed), None)

    async def _second_factor_refusal(self, db: AsyncSession, user: User, code: str) -> str | None:
        """Return why the second factor is not satisfied, or None; only an enrolled admin has one."""
        if not admin_totp_service.is_enabled(await admin_totp_service.get(db, user.id)):
            return None
        if not code:
            return "code_missing"
        if not await admin_totp_service.verify(db, self.settings, user, code):
            return "bad_code"
        return None

    async def _start_session(
        self, db: AsyncSession, request: Request, user: User, ip_hash: str, user_agent: str | None
    ) -> Response:
        """Open a session for the admin, end the one the browser held, and send them in."""
        previous = admin_session_service.cookie_token(request)
        if previous is not None:
            await admin_session_service.revoke(db, previous)
        token = await admin_session_service.create(
            db, user_id=user.id, ip_hash=ip_hash, user_agent=user_agent
        )
        await db.commit()
        await self.trail.write(request, AuditAction.SIGN_IN, admin_user_id=user.id)
        response = RedirectResponse(request.url_for("admin:index"), status_code=302)
        admin_session_service.set_cookie(response, token)
        csrf.clear_login_cookie(response)
        return response

    # ─── Every request ─────────────────────────────────────────────

    async def load(self, request: Request) -> Context | None:
        """Return who is signed in, or None; a session that no longer qualifies is deleted."""
        token = admin_session_service.cookie_token(request)
        if token is None:
            return None
        async with self.session_maker() as db:
            found = await admin_session_service.find(db, token)
            if found is None:
                await admin_session_service.revoke(db, token)
                await db.commit()
                return None
            session, user = found
            if await admin_session_service.touch(db, session):
                await db.commit()
            return Context(
                session=session,
                user=user,
                token=token,
                csrf=admin_session_service.csrf_token_for(self.settings, token),
            )

    async def authenticate(self, request: Request) -> Response | bool:
        """
        Re-check the admin on every admin request, then guard and record it.

        In order: the session must be live and its account still an active admin; a
        request that changes state must carry the CSRF token; an admin who has not
        enrolled the second factor is held to its page when the settings require it; a
        list page, a record page or a bulk action is written to the audit log.
        """
        context = await self.load(request)
        if context is None:
            return self._signed_out(request)
        request.state.admin_user = context.user
        request.state.admin_user_id = str(context.user.id)
        csrf.use_token(context.csrf)
        if request.method not in csrf.SAFE_METHODS and not csrf.tokens_match(
            context.csrf, await csrf.submitted_token(request)
        ):
            log.warning("Admin request refused: no valid CSRF token")
            raise HTTPException(status_code=403, detail=CSRF_MESSAGE)
        held = await self._enrolment_redirect(request, context.user)
        if held is not None:
            return held
        await self.trail.access(request, context.user.id)
        return True

    def _signed_out(self, request: Request) -> Response | bool:
        """Answer a request with no valid session: back to the sign-in page, dropping a dead cookie."""
        if admin_session_service.cookie_token(request) is None:
            return False
        response = RedirectResponse(request.url_for("admin:login"), status_code=302)
        admin_session_service.clear_cookie(response)
        return response

    async def _enrolment_redirect(self, request: Request, user: User) -> Response | None:
        """When two-factor is required and not enrolled, send the admin to the page that enrols it."""
        if not self.settings.admin_require_two_factor:
            return None
        if relative_path(request).startswith(ENROLMENT_PATHS):
            return None
        async with self.session_maker() as db:
            enrolled = admin_totp_service.is_enabled(await admin_totp_service.get(db, user.id))
        if enrolled:
            return None
        return RedirectResponse(request.url_for("admin:view-two-factor"), status_code=302)

    async def get_user_id(self, request: Request) -> str | None:
        user_id: str | None = getattr(request.state, "admin_user_id", None)
        return user_id

    # ─── Signing out ───────────────────────────────────────────────

    async def logout(self, request: Request) -> Response:
        """
        Serve the sign-out confirmation, or sign out on a POST that carries the token.

        A link that signed out on GET could be fired by any page; this asks for a click
        on a form that holds the CSRF token.
        """
        context = await self.load(request)
        if context is None:
            return self._to_login(request)
        csrf.use_token(context.csrf)
        if request.method == "GET":
            page: Response = await self.templates.TemplateResponse(request, LOGOUT_TEMPLATE, {})
            return page
        if not csrf.tokens_match(context.csrf, await csrf.submitted_token(request)):
            raise HTTPException(status_code=403, detail=CSRF_MESSAGE)
        async with self.session_maker() as db:
            await admin_session_service.revoke(db, context.token)
            await db.commit()
        await self.trail.write(request, AuditAction.SIGN_OUT, admin_user_id=context.user.id)
        return self._to_login(request)

    def _to_login(self, request: Request) -> Response:
        response = RedirectResponse(request.url_for("admin:login"), status_code=302)
        admin_session_service.clear_cookie(response)
        return response
