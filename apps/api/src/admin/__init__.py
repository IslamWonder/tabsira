"""
The admin area, served by the API at `/admin` (decision 14).

`install_admin` is all `src.main` needs. The pieces: `auth` (sign-in with a real account
that has `is_admin`, a second factor, a session of its own), `csrf`, `audit`, the views in
`views`, the dashboard, and `registry`, where other parts of the product add their views.
`docs/ADMIN.md` describes how it works and what it will never show.
"""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.admin.app import TabsiraAdmin
from src.admin.audit import AuditTrail
from src.admin.auth import AdminAuth
from src.admin.registry import load_extensions, register_view, registered_views
from src.admin.views import BUILT_IN_VIEWS
from src.config import Settings
from src.database import get_engine


def admin_session_maker() -> async_sessionmaker[AsyncSession]:
    """
    Return the session factory the admin uses.

    Its own, not the application's: sqladmin reconfigures the factory it is given
    (autoflush off), which must not leak into the rest of the API.
    """
    return async_sessionmaker(bind=get_engine(), expire_on_commit=False, class_=AsyncSession)


def install_admin(
    app: FastAPI,
    settings: Settings,
    *,
    session_maker: async_sessionmaker[AsyncSession] | None = None,
) -> TabsiraAdmin:
    """Mount the admin area on `app` with every built-in and registered view."""
    maker = session_maker or admin_session_maker()
    trail = AuditTrail(settings, maker)
    admin = TabsiraAdmin(
        app,
        settings=settings,
        session_maker=maker,
        auth=AdminAuth(settings, maker, trail),
        trail=trail,
    )
    for view in BUILT_IN_VIEWS:
        admin.register(view)
    load_extensions()
    for view in registered_views():
        admin.register(view)
    app.state.admin = admin
    return admin


__all__ = ["TabsiraAdmin", "admin_session_maker", "install_admin", "register_view"]
