"""
The extension point of the admin area: where another part of the product adds its views.

The admin's own views live in `src/admin/views/` (the rulings queue and the hadith rulings
among them). A part of the product built apart from the admin adds its views here, without
editing the admin:

    # src/admin/scripture.py
    from src.admin.registry import register_view

    @register_view
    class QuranVerseAdmin(ReadOnlyView, model=QuranVerse): ...

`install_admin` imports each module named in `EXTENSION_MODULES` that exists, so the
views a module registers are mounted after the built-in ones, in the order registered.
Nothing else has to change.

Every view passes `check_view_policy` when it is registered, and a view that does not is
refused at startup, not on the first request. The policy is decision 14 and decision 18
written as code:

- no view exports or imports: those are copies of data that leave the audit trail;
- every view names the columns it shows, in its list, on its record page and in its form:
  sqladmin shows every column of a model by default, which would put a hash, a token or a
  private answer on screen the day it is added to the model;
- the text of the Quran and of the hadiths is read-only: no create, edit or delete form;
- a hadith ruling is append-only: it can be created, never edited or deleted.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Sequence

from sqladmin import BaseView, ModelView

log = logging.getLogger("tabsira.admin.registry")

ViewClass = type[ModelView] | type[BaseView]

# Modules that register views when imported; one that does not exist is skipped.
EXTENSION_MODULES = ("src.admin.scripture",)

# The tables whose rows are scripture text, shown byte for byte and never written here.
SCRIPTURE_TEXT_TABLES = frozenset({"quran_verses", "hadiths"})
# The table of rulings: a ruling is recorded once, as a new row, and then stands.
RULING_TABLES = frozenset({"hadith_rulings"})

_registered: list[ViewClass] = []


class AdminPolicyError(RuntimeError):
    """A view breaks the rules every admin view follows."""


def _problems(view: ViewClass) -> list[str]:
    """List how `view` breaks the policy; empty when it keeps it."""
    if not issubclass(view, ModelView):
        return []
    found = []
    if view.can_export or view.can_import:
        found.append("it exports or imports data (set can_export and can_import to False)")
    if not view.column_list:
        found.append("it does not name its list columns (column_list)")
    if view.can_view_details and not view.column_details_list:
        found.append("it does not name its record page columns (column_details_list)")
    if (view.can_create or view.can_edit) and not view.form_columns:
        found.append("it does not name its form columns (form_columns)")
    table = getattr(getattr(view, "model", None), "__tablename__", "")
    if table in SCRIPTURE_TEXT_TABLES and (view.can_create or view.can_edit or view.can_delete):
        found.append(f"{table} is scripture text and read-only: no create, edit or delete form")
    if table in RULING_TABLES and (view.can_edit or view.can_delete):
        found.append(f"{table} is append-only: rulings are created, never edited or deleted")
    return found


def check_view_policy(view: ViewClass) -> None:
    """Raise `AdminPolicyError` when `view` breaks a rule every admin view follows."""
    problems = _problems(view)
    if problems:
        message = f"{view.__name__} is refused: " + "; ".join(problems)
        raise AdminPolicyError(message)


def register_view[V: ViewClass](view: V) -> V:
    """
    Add a view to the admin area; usable as a decorator, and returns the view.

    The view is checked now, so a bad one fails the import that registers it.
    """
    check_view_policy(view)
    if view not in _registered:
        _registered.append(view)
    return view


def registered_views() -> Sequence[ViewClass]:
    """Return the views registered so far, in the order they were registered."""
    return tuple(_registered)


def load_extensions(modules: Sequence[str] = EXTENSION_MODULES) -> None:
    """Import every extension module that exists, so it registers its views."""
    for name in modules:
        try:
            importlib.import_module(name)
        except ModuleNotFoundError as missing:
            if missing.name != name:
                raise
            log.debug("No admin extension %s", name)
