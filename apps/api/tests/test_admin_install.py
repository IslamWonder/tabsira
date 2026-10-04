"""Mounting the admin area: the feature flag, the menu, and the session factory it keeps to itself."""

from __future__ import annotations

from fastapi import FastAPI

from src.admin import admin_session_maker, install_admin
from src.database import get_engine, get_sessionmaker
from src.main import create_app
from tests.helpers import client_for


async def test_the_admin_is_not_mounted_while_its_feature_is_off(make_settings):
    app = create_app(make_settings(feature_admin=False))

    async with client_for(app) as http:
        for path in ("/admin", "/admin/", "/admin/login", "/admin/user/list"):
            response = await http.get(path)
            assert response.status_code == 404, path
            assert response.json()["error"] == "NOT_FOUND"
    assert not [route for route in app.routes if getattr(route, "path", "") == "/admin"]


async def test_the_admin_is_mounted_at_admin_while_its_feature_is_on(admin_app):
    mounted = [route for route in admin_app.routes if getattr(route, "path", "") == "/admin"]

    assert len(mounted) == 1
    async with client_for(admin_app, "https://admin.tabsira.test") as http:
        assert (await http.get("/admin/login")).status_code == 200
    # It is not part of the API's published schema.
    assert not [path for path in admin_app.openapi()["paths"] if path.startswith("/admin")]


def test_the_menu_lists_the_views_in_order_with_their_identities(admin_app):
    views = [(view.identity, view.category) for view in admin_app.state.admin.views]

    assert views == [
        ("user", "Accounts"),
        ("session", "Accounts"),
        ("consent", "Accounts"),
        ("rulings-queue", "Scripture"),
        ("hadith-ruling", "Scripture"),
        ("ontology-candidate", "Ontology"),
        ("ontology-entity", "Ontology"),
        ("learning-path-version", "Learning path"),
        ("learning-domain", "Learning path"),
        ("learning-unit", "Learning path"),
        ("geo-name", "Places"),
        ("admin-audit-log", "Security"),
        ("two-factor", "Security"),
    ]


def test_the_admin_has_a_session_factory_of_its_own_so_sqladmin_cannot_change_the_apis(
    make_settings,
):
    app = FastAPI()

    admin = install_admin(app, make_settings())

    assert admin.session_maker is not get_sessionmaker()
    assert admin.session_maker.kw["bind"] is get_engine()
    # sqladmin switched autoflush off on the factory it was given, not on the API's.
    assert admin.session_maker.kw["autoflush"] is False
    assert get_sessionmaker().kw.get("autoflush", True) is True


def test_the_default_factory_is_built_on_the_applications_engine():
    maker = admin_session_maker()

    assert maker.kw["bind"] is get_engine()
    assert maker.kw["expire_on_commit"] is False
