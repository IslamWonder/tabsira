"""
The public identity of an account: a handle and a name chosen on purpose.

A person who wants to publish picks a handle (their address, `/u/<handle>`). Beside it a public
page shows the person's real full name (`display_name`) only while the `public_full_name`
consent is given (decision 64); withdrawn or never given, the handle is all it says. A handle
is unique whatever its case. The one thing read from the profile is the country the person
declared, and only while its own `public_country` consent is given (decision 67); nothing is
guessed or copied from anything else.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Collection

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors import AppError, ErrorCode
from src.models.profile import Profile
from src.models.user import HANDLE_PATTERN, User
from src.schemas.geo import PublicCountryOut
from src.services import geo_service

_HANDLE = re.compile(HANDLE_PATTERN)
# Names that say "this is the platform" or "this is staff"; nobody may take them.
RESERVED_HANDLES = frozenset(
    {
        "admin",
        "administrator",
        "tabsira",
        "support",
        "moderator",
        "mod",
        "staff",
        "help",
        "root",
        "system",
        "api",
        "www",
        "official",
        "me",
        "تبصرة",
        "ادارة",
        "الادارة",
        "الإدارة",
        "إدارة",
        "مشرف",
        "دعم",
        "الدعم",
    }
)
# A handle that starts like one of these passes for the platform or for staff: refused whatever
# follows (`tabsira_help`, `admin2`). Compared after the handle is folded to lower case.
RESERVED_PREFIXES = (
    "tabsira",
    "admin",
    "support",
    "moderator",
    "تبصر",
    "مشرف",
    "ادارة",
    "إدارة",
    "الإدارة",
    "الادارة",
)


def clean_handle(raw: str) -> str:
    """Return the handle in its stored form: compatibility forms folded, outer space removed."""
    return unicodedata.normalize("NFKC", raw).strip()


def handle_problem(handle: str) -> str | None:
    """Return why a cleaned handle cannot be used, or None when it can."""
    if _HANDLE.match(handle) is None:
        return (
            "must be 3 to 30 letters, digits or underscores, start with a letter, "
            "and carry no diacritics"
        )
    if handle.lower() in RESERVED_HANDLES or handle.lower().startswith(RESERVED_PREFIXES):
        return "is reserved"
    return None


def shown_name(user: User) -> str | None:
    """
    Return the name a public answer carries beside the handle, or None for the handle alone.

    The real full name, and only while the person's consent to show it is given; every public
    answer that names an account goes through here, so withdrawing the consent is enough.
    """
    return user.display_name if user.public_full_name else None


async def shown_countries(
    db: AsyncSession, user_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, PublicCountryOut]:
    """
    Return the country each of these accounts shows publicly, in one query; absent means none.

    Only a declared country whose `public_country` consent is given, and only one GeoNames still
    names. The public profile and the author line of a post read it; no other answer does.
    """
    if not user_ids:
        return {}
    rows = (
        await db.execute(
            select(Profile.user_id, Profile.country).where(
                Profile.user_id.in_(set(user_ids)),
                Profile.show_country.is_(True),
                Profile.country.is_not(None),
            )
        )
    ).all()
    if not rows:
        return {}
    labels = await geo_service.country_labels(db)
    return {
        user_id: PublicCountryOut(code=code, name=labels[code])
        for user_id, code in rows
        if code in labels
    }


def _taken() -> AppError:
    return AppError(ErrorCode.HANDLE_TAKEN, "This handle is taken.", status_code=409)


async def set_public_identity(db: AsyncSession, user: User, *, handle: str) -> User:
    """
    Give the account its handle, or change it.

    The handle must be free, whatever the case of the one that holds it; the person's own
    current handle counts as free, so they may change only its case.
    """
    holder = await db.scalar(
        select(User.id).where(func.lower(User.handle) == handle.lower(), User.id != user.id)
    )
    if holder is not None:
        raise _taken()
    user.handle = handle
    try:
        # A savepoint, so losing a race for the handle leaves the transaction usable.
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise _taken() from None
    return user


async def find_member(db: AsyncSession, handle: str) -> User | None:
    """Return the live account that holds `handle`, in any case, or None."""
    found: User | None = await db.scalar(
        select(User).where(
            func.lower(User.handle) == clean_handle(handle).lower(),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    return found
