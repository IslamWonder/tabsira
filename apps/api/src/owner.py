"""
Who owns what a request reads or writes: an account, or a guest.

Every route of the scan workflow resolves its caller to an `Owner` and filters
every query by it, so knowing an id grants nothing: another owner's scan or
insight answers 404, exactly like one that does not exist. A signed-in caller
is always the account, even when the browser still holds a guest cookie (the
guest's rows are merged at sign-in). A caller with neither gets a new guest
only on a route that saves something.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated, Any, Protocol

from fastapi import Depends, Request, Response
from sqlalchemy import ColumnElement

from src.deps import DbDep, OptionalUser, SettingsDep
from src.errors import AppError, ErrorCode
from src.services import guest_service


class Owned(Protocol):
    """A model with the two owner columns."""

    user_id: Any
    guest_key: Any


@dataclass(frozen=True)
class Owner:
    """An account (`user_id`) or a guest (`guest_key`), never both."""

    user_id: uuid.UUID | None = None
    guest_key: str | None = None

    @property
    def is_guest(self) -> bool:
        return self.user_id is None

    def where(self, model: type[Owned]) -> ColumnElement[bool]:
        """Return the condition that keeps the rows of `model` this owner owns."""
        if self.user_id is not None:
            condition: ColumnElement[bool] = model.user_id == self.user_id
        else:
            condition = model.guest_key == self.guest_key
        return condition

    def owns(self, row: Owned) -> bool:
        if self.user_id is not None:
            return bool(row.user_id == self.user_id)
        return row.guest_key is not None and row.guest_key == self.guest_key

    def columns(self) -> dict[str, Any]:
        """Return the owner columns of a new row."""
        return {"user_id": self.user_id, "guest_key": self.guest_key}


# What a 404 names; module constants, so a raise never carries a bare literal.
SCAN = "scan"
INSIGHT = "insight"
PLACE = "place"
TREASURE = "treasure"


def not_found(what: str) -> AppError:
    """Return the answer for a missing row and for another owner's row alike."""
    return AppError(ErrorCode.NOT_FOUND, f"No such {what}.", status_code=404)


async def optional_owner(
    request: Request, db: DbDep, settings: SettingsDep, user: OptionalUser
) -> Owner | None:
    """Return the caller's account, else the caller's live guest, else None."""
    if user is not None:
        return Owner(user_id=user.id)
    token = guest_service.cookie_token(request, settings)
    if token is None:
        return None
    guest = await guest_service.find(db, settings, token)
    if guest is None:
        return None
    await db.commit()
    return Owner(guest_key=guest.key)


OptionalOwner = Annotated[Owner | None, Depends(optional_owner)]


async def owner_for_write(
    request: Request, response: Response, db: DbDep, settings: SettingsDep, owner: OptionalOwner
) -> Owner:
    """
    Return the caller as an owner, making a guest (and its cookie) for a newcomer.

    A guest that saves something gets its cookie again, so a guest that keeps
    coming back keeps its cookie as long as the server keeps its rows.
    """
    if owner is not None:
        token = guest_service.cookie_token(request, settings) if owner.is_guest else None
        if token is not None:
            guest_service.set_cookie(response, settings, token)
        return owner
    token, guest = await guest_service.create(db, settings)
    await db.commit()
    guest_service.set_cookie(response, settings, token)
    return Owner(guest_key=guest.key)


WritingOwner = Annotated[Owner, Depends(owner_for_write)]
