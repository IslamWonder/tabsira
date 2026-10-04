"""
The extension point, and the policy it enforces on every view that is added through it.

The scripture store is not built yet, so its tables are stood in for by throwaway models
that carry the same table names; the policy keys on those names.
"""

from __future__ import annotations

import importlib
import sys
import types

import pytest
from fastapi import FastAPI
from sqladmin import BaseView, ModelView, action, expose
from sqlalchemy import Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from starlette.responses import PlainTextResponse

from src.admin import install_admin, register_view, registry
from src.admin.base import AdminView, ReadOnlyView
from src.admin.registry import AdminPolicyError, check_view_policy


class Standin(DeclarativeBase):
    """A metadata of its own: these tables are never created."""


def table_model(name: str) -> type[Standin]:
    return type(
        name.title().replace("_", ""),
        (Standin,),
        {
            "__tablename__": name,
            "id": mapped_column(Integer, primary_key=True),
            "body": mapped_column(Text),
            "__annotations__": {"id": Mapped[int], "body": Mapped[str]},
        },
    )


QuranVerse = table_model("quran_verses")
Hadith = table_model("hadiths")
HadithRuling = table_model("hadith_rulings")
Widget = table_model("widgets")


@pytest.fixture(autouse=True)
def clean_registry(monkeypatch):
    """Every test starts with nothing registered, and leaves nothing behind."""
    monkeypatch.setattr(registry, "_registered", [])


def read_only(model, **attributes):
    return type(
        f"{model.__name__}Admin",
        (ReadOnlyView,),
        {
            "name": model.__name__,
            "column_list": [model.id],
            "column_details_list": [model.id],
            **attributes,
        },
        model=model,
    )


def editable(model, **attributes):
    return type(
        f"{model.__name__}Admin",
        (AdminView,),
        {
            "name": model.__name__,
            "column_list": [model.id],
            "column_details_list": [model.id],
            "form_columns": [model.body],
            **attributes,
        },
        model=model,
    )


# ─── The policy ────────────────────────────────────────────────────


def test_a_read_only_view_of_scripture_text_passes():
    for model in (QuranVerse, Hadith):
        check_view_policy(read_only(model))


@pytest.mark.parametrize("flag", ["can_create", "can_edit", "can_delete"])
@pytest.mark.parametrize("model", [QuranVerse, Hadith], ids=["quran", "hadith"])
def test_scripture_text_can_never_have_a_create_edit_or_delete_form(model, flag):
    flags = {"can_create": False, "can_edit": False, "can_delete": False, flag: True}
    view = editable(model, **flags)

    with pytest.raises(AdminPolicyError, match="scripture text and read-only"):
        check_view_policy(view)


def test_a_ruling_can_be_created_but_never_edited_or_deleted():
    check_view_policy(editable(HadithRuling, can_edit=False, can_delete=False, can_create=True))

    for flag in ("can_edit", "can_delete"):
        flags = {"can_create": True, "can_edit": False, "can_delete": False, flag: True}
        with pytest.raises(AdminPolicyError, match="append-only"):
            check_view_policy(editable(HadithRuling, **flags))


@pytest.mark.parametrize("flag", ["can_export", "can_import"])
def test_no_view_exports_or_imports(flag):
    with pytest.raises(AdminPolicyError, match="exports or imports"):
        check_view_policy(read_only(Widget, **{flag: True}))


def test_a_view_must_name_its_columns_so_a_new_column_is_never_shown_by_default():
    unnamed_list = read_only(Widget, column_list=[])
    unnamed_details = read_only(Widget, column_details_list=[])
    unnamed_form = editable(Widget, form_columns=[])

    for view, what in (
        (unnamed_list, "column_list"),
        (unnamed_details, "column_details_list"),
        (unnamed_form, "form_columns"),
    ):
        with pytest.raises(AdminPolicyError, match=what):
            check_view_policy(view)
    # A view with no record page need not name what that page shows.
    check_view_policy(read_only(Widget, column_details_list=[], can_view_details=False))


def test_every_problem_is_listed_in_one_message():
    view = editable(Hadith, can_export=True, can_create=True, form_columns=[])

    with pytest.raises(AdminPolicyError) as refused:
        check_view_policy(view)

    message = str(refused.value)
    assert message.startswith("HadithsAdmin is refused:")
    assert "exports or imports" in message
    assert "form_columns" in message
    assert "scripture text" in message


def test_a_page_that_is_not_a_model_view_has_nothing_to_check():
    class Page(BaseView):
        name = "Page"

        @expose("/page", methods=["GET"], identity="page")
        async def show(self, request):
            return PlainTextResponse("page")

    check_view_policy(Page)


# ─── Registering ───────────────────────────────────────────────────


def test_register_view_checks_the_view_and_returns_it_so_it_works_as_a_decorator():
    view = read_only(Widget)

    assert register_view(view) is view
    assert registry.registered_views() == (view,)
    # Registering twice is one registration.
    register_view(view)
    assert registry.registered_views() == (view,)

    with pytest.raises(AdminPolicyError):
        register_view(read_only(QuranVerse, can_edit=True))
    assert registry.registered_views() == (view,)


def test_registered_views_keep_the_order_they_were_added_in():
    first, second = read_only(Widget), read_only(Hadith)

    register_view(first)
    register_view(second)

    assert registry.registered_views() == (first, second)


# ─── Loading extension modules ─────────────────────────────────────


def test_a_module_that_does_not_exist_is_skipped_quietly():
    registry.load_extensions(("src.admin.no_such_extension",))

    assert registry.registered_views() == ()


def test_the_shipped_extension_module_is_the_scripture_one():
    assert registry.EXTENSION_MODULES == ("src.admin.scripture",)
    # It does not exist until the scripture store is merged, and that is not an error.
    registry.load_extensions()


def test_a_module_that_exists_is_imported_and_registers_its_views(monkeypatch):
    view = read_only(Widget)
    module = types.ModuleType("src.admin.fake_extension")
    module.__dict__["register"] = lambda: register_view(view)
    monkeypatch.setitem(sys.modules, "src.admin.fake_extension", module)
    real_import = importlib.import_module

    def import_and_register(name):
        found = real_import(name)
        if name == "src.admin.fake_extension":
            found.register()
        return found

    monkeypatch.setattr(registry.importlib, "import_module", import_and_register)

    registry.load_extensions(("src.admin.fake_extension",))

    assert registry.registered_views() == (view,)


def test_a_module_that_fails_to_import_something_else_is_not_hidden(monkeypatch):
    def broken(name):
        raise ModuleNotFoundError("No module named 'dependency'", name="dependency")

    monkeypatch.setattr(registry.importlib, "import_module", broken)

    with pytest.raises(ModuleNotFoundError, match="dependency"):
        registry.load_extensions(("src.admin.scripture",))


# ─── Installing what was registered ────────────────────────────────


def test_install_mounts_registered_views_after_the_built_in_ones_and_makes_actions_post(
    make_settings,
):
    class Pinged(AdminView, model=Widget):
        name = "Widget"
        name_plural = "Widgets"
        column_list = [Widget.id]
        column_details_list = [Widget.id]
        form_columns = [Widget.body]

        @action(name="ping", label="Ping")
        async def ping(self, request):
            return PlainTextResponse("pong")

    register_view(Pinged)
    app = FastAPI()

    admin = install_admin(app, make_settings())

    identities = [view.identity for view in admin.views]
    assert identities[-1] == "widgets"
    assert identities[0] == "user"
    routes = {
        route.name: route for route in admin.admin.router.routes if getattr(route, "name", None)
    }
    assert routes["action-widgets-ping"].methods == {"POST"}
    assert routes["logout"].methods >= {"GET", "POST"}


def test_install_refuses_a_registered_view_that_was_changed_to_break_the_policy_afterwards(
    make_settings,
):
    view = read_only(Widget)
    register_view(view)
    view.can_export = True

    with pytest.raises(AdminPolicyError):
        install_admin(FastAPI(), make_settings())


def test_the_standin_models_are_plain_model_views():
    assert issubclass(read_only(Widget), ModelView)
