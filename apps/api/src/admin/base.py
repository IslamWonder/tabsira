"""
The base classes of every admin view, and the helpers an action uses.

A view starts from `ReadOnlyView` and gains only what it needs: the admin is for
reviewing, and the few things an admin changes are named one by one in their views. No
view exports: a CSV of accounts or consents is a copy of private data that leaves the
audit trail, so `register_view` refuses a view that switches `can_export` or `can_import`
on.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqladmin import ModelView
from starlette import status
from starlette.datastructures import URL
from starlette.requests import Request
from starlette.responses import RedirectResponse

from src.admin.audit import CHANGED_FIELDS_ATTR
from src.models.user import User

PAGE_SIZE = 50
PAGE_SIZE_OPTIONS = [25, 50, 100]


class AdminView(ModelView):
    """
    The base of every admin model view.

    It names the fields an edit changed, for the audit log: the submitted form is
    compared with the record, and only the names of the differing fields are kept. A view
    that overrides `on_model_change` must still call this one.
    """

    can_export = False
    can_import = False
    page_size = PAGE_SIZE
    page_size_options = PAGE_SIZE_OPTIONS

    async def on_model_change(
        self, data: dict[str, Any], model: Any, is_created: bool, request: Request
    ) -> None:
        if is_created:
            changed = sorted(data)
        else:
            changed = sorted(
                name for name, value in data.items() if getattr(model, name, None) != value
            )
        setattr(request.state, CHANGED_FIELDS_ATTR, changed)


class ReadOnlyView(AdminView):
    """A view with no create, edit or delete form: it lists and shows."""

    can_create = False
    can_edit = False
    can_delete = False


def labelled(columns: Iterable[Any]) -> dict[Any, str]:
    """Return a readable label for each column: `display_name` is shown as `Display name`."""
    return {column: str(column.key).replace("_", " ").capitalize() for column in columns}


def selected_pks(request: Request) -> list[str]:
    """Return the primary keys an action was invoked on (`?pks=a,b`), without the empty ones."""
    return [pk for pk in request.query_params.get("pks", "").split(",") if pk]


def selected_uuids(request: Request) -> list[uuid.UUID]:
    """Return the selected keys that are UUIDs; anything else cannot name a record and is dropped."""
    found: list[uuid.UUID] = []
    for pk in selected_pks(request):
        try:
            found.append(uuid.UUID(pk))
        except ValueError:
            continue
    return found


def current_admin(request: Request) -> uuid.UUID:
    """Return the id of the admin who is making this request; `authenticate` has set it."""
    return uuid.UUID(request.state.admin_user_id)


def current_user(request: Request) -> User:
    """Return the admin's account as `authenticate` loaded it for this request."""
    user: User = request.state.admin_user
    return user


def back_to_list(request: Request, identity: str, error: str | None = None) -> RedirectResponse:
    """
    Send the browser back to a view's list after an action, with an error to show if any.

    A 303, so the browser follows the POST of the action with a GET. The address is built
    from the view's identity, never taken from the request: nothing in it can redirect a
    browser anywhere else.
    """
    url: URL = request.url_for("admin:list", identity=identity)
    if error:
        url = url.include_query_params(error=error)
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)
