"""
Accounts in the admin area: users, their sessions and their consents.

Privacy first. Each view lists the columns it shows by name, so a column added to a model
later never appears by itself. What is never shown, anywhere: the password hash, the
session token hash, and everything a person answered in their profile (religious
background, gender, age range, goals); there is no profile view at all, because nothing
an admin does here needs one.
"""

from __future__ import annotations

from typing import Any

from sqladmin import action
from sqladmin.filters import BooleanFilter, StaticValuesFilter
from sqlalchemy import delete
from starlette.requests import Request
from starlette.responses import Response

from src.admin.base import (
    AdminView,
    ReadOnlyView,
    back_to_list,
    current_admin,
    labelled,
    selected_uuids,
)
from src.models.consent import Consent, ConsentKind
from src.models.session import Session
from src.models.user import User

CATEGORY = "Accounts"
CATEGORY_ICON = "fa-solid fa-users"
NOTHING_SELECTED = "Select at least one record first."


class UserAdmin(AdminView, model=User):
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"
    category = CATEGORY
    category_icon = CATEGORY_ICON

    column_list = [
        User.email,
        User.display_name,
        User.is_active,
        User.is_admin,
        User.email_verified_at,
        User.created_at,
        User.updated_at,
    ]
    column_details_list = [
        User.id,
        User.email,
        User.display_name,
        User.is_active,
        User.is_admin,
        User.email_verified_at,
        User.created_at,
        User.updated_at,
        User.deleted_at,
    ]
    column_labels = labelled(column_details_list)
    column_searchable_list = [User.email, User.display_name]
    column_sortable_list = [User.email, User.display_name, User.created_at, User.updated_at]
    column_default_sort = [(User.created_at, True)]
    column_filters = [
        BooleanFilter(User.is_active, "Active"),
        BooleanFilter(User.is_admin, "Admin"),
    ]
    # The two things an admin may change: a name that has to go, and whether the account is
    # active. Admin rights are given and taken on the command line, never from here.
    form_columns = [User.display_name, User.is_active]
    can_create = False
    can_delete = False

    async def on_model_change(
        self, data: dict[str, Any], model: Any, is_created: bool, request: Request
    ) -> None:
        if data.get("is_active") is False and model.id == current_admin(request):
            message = "You cannot deactivate your own account."
            raise ValueError(message)
        await super().on_model_change(data, model, is_created, request)


class SessionAdmin(ReadOnlyView, model=Session):
    name = "Session"
    name_plural = "Sessions"
    icon = "fa-solid fa-key"
    category = CATEGORY
    category_icon = CATEGORY_ICON

    # Never the token hash, and not the address hash either: nothing here needs them.
    column_list = [
        Session.id,
        Session.user_id,
        Session.created_at,
        Session.last_seen_at,
        Session.expires_at,
        Session.user_agent,
    ]
    column_details_list = column_list
    column_labels = labelled(column_list)
    column_sortable_list = [Session.created_at, Session.last_seen_at, Session.expires_at]
    column_default_sort = [(Session.last_seen_at, True)]
    column_searchable_list = [Session.user_agent]

    @action(
        name="revoke",
        label="Revoke",
        confirmation_message="Sign the people behind the selected sessions out?",
    )
    async def revoke(self, request: Request) -> Response:
        ids = selected_uuids(request)
        if not ids:
            return back_to_list(request, self.identity, NOTHING_SELECTED)
        async with self.session_maker() as db:
            await db.execute(delete(Session).where(Session.id.in_(ids)))
            await db.commit()
        return back_to_list(request, self.identity)


class ConsentAdmin(ReadOnlyView, model=Consent):
    name = "Consent"
    name_plural = "Consents"
    icon = "fa-solid fa-file-signature"
    category = CATEGORY
    category_icon = CATEGORY_ICON

    column_list = [
        Consent.id,
        Consent.user_id,
        Consent.kind,
        Consent.version,
        Consent.granted,
        Consent.created_at,
    ]
    column_details_list = column_list
    column_labels = labelled(column_list)
    column_sortable_list = [Consent.created_at, Consent.kind, Consent.version]
    column_default_sort = [(Consent.created_at, True)]
    column_filters = [
        BooleanFilter(Consent.granted, "Granted"),
        StaticValuesFilter(
            Consent.kind, [(kind.value, kind.value) for kind in ConsentKind], "Kind"
        ),
    ]
