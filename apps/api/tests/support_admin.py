"""
Fixtures and helpers for the admin area's tests, loaded as a pytest plugin by conftest.

The admin keeps its own sessions and writes its own audit rows, so its views cannot use the
request-scoped test session the account tests override `get_db` with. Instead its session
factory is bound to the test's connection: every request opens a session on that one
connection, so what a request commits is visible to the next and all of it rolls back
with the test.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable
from typing import Any

import pyotp
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import src.admin
from src.config import Settings
from src.main import create_app
from src.models import (
    AdminAuditLog,
    LearningDomain,
    LearningPathVersion,
    LearningUnit,
    OntologyCandidate,
    OntologyEntity,
    User,
)

ADMIN_PASSWORD = "an admin passphrase"
ADMIN_EMAIL = "admin@example.com"
ADMIN_ORIGIN = "https://admin.tabsira.test"
TOKEN_FIELD = re.compile(r'name="csrf_token" value="([^"]*)"')
META_TOKEN = re.compile(r'<meta name="csrf-token" content="([^"]*)"')


@pytest.fixture
def admin_maker(db_session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    """Sessions on the test's own connection, as the admin's factory."""
    return async_sessionmaker(bind=db_session.bind, expire_on_commit=False)


@pytest.fixture
def make_admin_app(
    make_settings: Callable[..., Settings],
    admin_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., FastAPI]:
    """Build an application whose admin runs on the test connection; settings may be overridden."""
    monkeypatch.setattr(src.admin, "admin_session_maker", lambda: admin_maker)

    def build(**overrides: Any) -> FastAPI:
        values: dict[str, Any] = {
            "password_bcrypt_rounds": 4,
            "admin_totp_encryption_key": Fernet.generate_key().decode(),
            "hash_secret": "a-test-hash-secret-long-enough-for-hmac",
        }
        return create_app(make_settings(**{**values, **overrides}))

    return build


@pytest.fixture
def admin_app(make_admin_app: Callable[..., FastAPI]) -> FastAPI:
    """An application whose admin runs on the test connection."""
    return make_admin_app()


def browser(application: FastAPI) -> AsyncClient:
    """A browser on the admin's own origin: HTTPS, the admin host, a cookie jar."""
    return AsyncClient(
        transport=ASGITransport(app=application, raise_app_exceptions=False),
        base_url=ADMIN_ORIGIN,
        headers={"Origin": ADMIN_ORIGIN},
    )


@pytest.fixture
async def anon(admin_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """A browser that has not signed in."""
    async with browser(admin_app) as http:
        yield http


@pytest.fixture
async def make_admin(make_user: Callable[..., Any]) -> Callable[..., Any]:
    """Create an admin account in the database."""

    async def create(email: str = ADMIN_EMAIL, **columns: Any) -> User:
        columns.setdefault("is_admin", True)
        return await make_user(email, ADMIN_PASSWORD, display_name="Admin", **columns)

    return create


def token_of(page: Response) -> str:
    """Return the CSRF token a rendered page carries, in a form field or the meta tag."""
    found = TOKEN_FIELD.search(page.text) or META_TOKEN.search(page.text)
    assert found, "the page has no CSRF token"
    return found.group(1)


async def sign_in(
    http: AsyncClient,
    email: str = ADMIN_EMAIL,
    password: str = ADMIN_PASSWORD,
    code: str = "",
) -> Response:
    """Fetch the sign-in form and submit it, as a browser does."""
    page = await http.get("/admin/login")
    return await http.post(
        "/admin/login",
        data={"email": email, "password": password, "code": code, "csrf_token": token_of(page)},
    )


@pytest.fixture
async def admin(
    admin_app: FastAPI, make_admin: Callable[..., Any]
) -> AsyncIterator[tuple[AsyncClient, User]]:
    """A browser signed in as an admin, and that admin's account."""
    user = await make_admin()
    async with browser(admin_app) as http:
        response = await sign_in(http)
        assert response.status_code == 302, response.text
        yield http, user


async def csrf_of(http: AsyncClient) -> str:
    """Return the CSRF token of the signed-in session, from the dashboard's meta tag."""
    return token_of(await http.get("/admin/"))


async def enable_two_factor(http: AsyncClient, moving_clock: Any) -> str:
    """Turn the second factor on for the signed-in admin through the page; return the secret."""
    token = await csrf_of(http)
    await http.post("/admin/two-factor/start", data={"csrf_token": token})
    shown = re.search(r'id="totp-secret">([A-Z2-7 ]+)<', (await http.get("/admin/two-factor")).text)
    assert shown, "the page shows no secret"
    secret = shown.group(1).replace(" ", "")
    code = pyotp.TOTP(secret).at(int(moving_clock.now.timestamp()))
    done = await http.post("/admin/two-factor/confirm", data={"csrf_token": token, "code": code})
    assert done.status_code == 200, done.text
    return secret


async def audit_rows(db_session: AsyncSession) -> list[AdminAuditLog]:
    """Return every audit row, oldest first."""
    return list((await db_session.scalars(select(AdminAuditLog).order_by(AdminAuditLog.id))).all())


# ─── Rows of the data the admin shows ──────────────────────────────

SHA = "0" * 64


def path_version(name: str = "tabsira-masar-1.0", **columns: Any) -> LearningPathVersion:
    values = {
        "path_version": name,
        "title": "مسار",
        "version": "1.0",
        "source_file": f"{name}.json",
        "source_sha256": SHA,
        "domain_count": 1,
        "unit_count": 1,
        "depths": [],
        "coverage": [],
    }
    return LearningPathVersion(**{**values, **columns})


def path_domain(
    name: str = "tabsira-masar-1.0", domain_id: str = "T00", **columns: Any
) -> LearningDomain:
    values = {
        "path_version": name,
        "id": domain_id,
        "position": 1,
        "title": "مفاتيح النظر والتعلم",
        "function": "ضبط الانتقال من الصورة إلى المعرفة",
        "goal": "أن يتعلم المستعمل كيف تنتقل المنصة من المرئي إلى المعنى",
        "concepts": ["ملاحظة", "دليل"],
    }
    return LearningDomain(**{**values, **columns})


def path_unit(
    name: str = "tabsira-masar-1.0", unit_id: str = "T00_01", **columns: Any
) -> LearningUnit:
    values = {
        "path_version": name,
        "id": unit_id,
        "domain_id": "T00",
        "position": 1,
        "title": "يميّز الشيء الظاهر عن التخمين",
        "objectives": ["يميّز الشيء الظاهر عن التخمين"],
        "prerequisites": [],
        "depths": ["L0"],
        "concepts": ["ملاحظة"],
        "evidence_refs": ["quran:2:255"],
        "source_anchors": [],
    }
    return LearningUnit(**{**values, **columns})


def candidate(term: str = "طائرة مسيرة", **columns: Any) -> OntologyCandidate:
    values = {"kind": "label", "term": term, "term_norm": term, "count": 3, "sources": ["detector"]}
    return OntologyCandidate(**{**values, **columns})


def entity(entity_id: str = "E001", **columns: Any) -> OntologyEntity:
    values = {
        "id": entity_id,
        "label_ar": "سماء",
        "related_objects": ["سماء", "أفق"],
        "actions_and_uses": ["نظر"],
        "contextual_concepts": ["خلق"],
        "domain": "السماء والطقس",
        "raw": {"row": 6},
        "label_norm": "سماء",
        "related_norm": ["سماء", "افق"],
        "search_text": "سماء افق",
        "source_sha256": SHA,
    }
    return OntologyEntity(**{**values, **columns})
