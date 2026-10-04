"""
The public identity of an account: a handle and a name chosen on purpose.

The account's own display name may be a real name, or the one Google gave, so it is never
shown on the network. A person who wants to publish picks a handle (their address,
`/u/<handle>`) and a public name here; the two are the only things any public page says
about them. A handle is unique whatever its case. Nothing here reads, guesses or copies
anything from the profile.
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors import AppError, ErrorCode
from src.models.user import HANDLE_PATTERN, PUBLIC_NAME_MAX, User

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
# An address or a link in a name would put a stranger's contact details on a public page.
_NAME_FORBIDDEN = re.compile(r"[@<>]|https?:|www\.", re.IGNORECASE)
_SPACES = re.compile(r"\s+")


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
    if handle.lower() in RESERVED_HANDLES:
        return "is reserved"
    return None


def clean_public_name(raw: str) -> str:
    """Return the name with its whitespace collapsed to single spaces."""
    return _SPACES.sub(" ", unicodedata.normalize("NFKC", raw)).strip()


def public_name_problem(name: str) -> str | None:
    """Return why a cleaned public name cannot be used, or None when it can."""
    if not 1 <= len(name) <= PUBLIC_NAME_MAX:
        return f"must be 1 to {PUBLIC_NAME_MAX} characters"
    if any(unicodedata.category(char).startswith("C") for char in name):
        return "must not contain control characters"
    if _NAME_FORBIDDEN.search(name):
        return "must not contain an address or a link"
    return None


def _taken() -> AppError:
    return AppError(ErrorCode.HANDLE_TAKEN, "This handle is taken.", status_code=409)


async def set_public_identity(
    db: AsyncSession, user: User, *, handle: str, public_name: str
) -> User:
    """
    Give the account its handle and public name, or change them.

    The handle must be free, whatever the case of the one that holds it; the person's own
    current handle counts as free, so they may change only its case, or only their name.
    """
    holder = await db.scalar(
        select(User.id).where(func.lower(User.handle) == handle.lower(), User.id != user.id)
    )
    if holder is not None:
        raise _taken()
    user.handle = handle
    user.public_name = public_name
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
