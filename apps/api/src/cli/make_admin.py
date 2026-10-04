"""
Make an account an admin, take it away, or clear an admin's second factor.

    uv run python -m src.cli.make_admin you@example.com
    uv run python -m src.cli.make_admin you@example.com --revoke
    uv run python -m src.cli.make_admin you@example.com --reset-two-factor

The admin area signs in with a real account that has `is_admin`; there is no way to
become one from the web, so this is how the first admin is made, and how a lost
authenticator is dealt with when the recovery codes are lost too. Each change is
written to the audit log. Revoking takes effect at once (every admin request checks the
flag) and also deletes the account's admin sessions and second factor. Exits 0 on
success, 1 when the account is not found or cannot be used, or the database is out of
reach.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import ConfigError
from src.database import dispose_engine, get_sessionmaker
from src.models.admin_audit import AuditAction
from src.models.user import User
from src.services import (
    admin_audit_service,
    admin_session_service,
    admin_totp_service,
    auth_service,
)

CLI_REASON = "cli"


class Change(StrEnum):
    GRANT = "grant"
    REVOKE = "revoke"
    RESET_TWO_FACTOR = "reset_two_factor"


@dataclass(frozen=True, slots=True)
class Options:
    email: str
    change: Change


def _say(line: str) -> None:
    sys.stdout.write(f"{line}\n")


def _refuse(line: str) -> int:
    sys.stderr.write(f"{line}\n")
    return 1


def _parse_arguments(argv: Sequence[str] | None) -> Options:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.make_admin",
        description="Make an account an admin, revoke it, or reset its second factor.",
    )
    parser.add_argument("email", help="the e-mail address of the account")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--revoke", action="store_true", help="remove admin rights")
    group.add_argument(
        "--reset-two-factor",
        action="store_true",
        help="remove the admin's second factor, so it can enrol again",
    )
    args = parser.parse_args(argv)
    change = Change.GRANT
    if args.revoke:
        change = Change.REVOKE
    elif args.reset_two_factor:
        change = Change.RESET_TWO_FACTOR
    return Options(email=args.email, change=change)


async def _audit(db: AsyncSession, user: User, action: AuditAction) -> None:
    await admin_audit_service.record(db, action=action, admin_user_id=user.id, reason=CLI_REASON)


async def _grant(db: AsyncSession, user: User) -> int:
    if not auth_service.can_sign_in(user):
        return _refuse("This account is disabled or deleted, so it cannot be made an admin.")
    if user.is_admin:
        _say("This account is already an admin; nothing changed.")
        return 0
    user.is_admin = True
    await _audit(db, user, AuditAction.ADMIN_GRANTED)
    _say("This account is now an admin.")
    if user.password_hash is None:
        _say(
            "It has no password, and the admin area signs in with one: "
            "set it with «forgot password» on the sign-in page."
        )
    return 0


async def _revoke(db: AsyncSession, user: User) -> int:
    if not user.is_admin:
        _say("This account is not an admin; nothing changed.")
        return 0
    user.is_admin = False
    await admin_session_service.revoke_all(db, user.id)
    await admin_totp_service.disable(db, user.id)
    await _audit(db, user, AuditAction.ADMIN_REVOKED)
    _say("Admin rights removed; its admin sessions and second factor are deleted.")
    return 0


async def _reset_two_factor(db: AsyncSession, user: User) -> int:
    if not user.is_admin:
        return _refuse("This account is not an admin.")
    await admin_totp_service.disable(db, user.id)
    await admin_session_service.revoke_all(db, user.id)
    await _audit(db, user, AuditAction.TWO_FACTOR_RESET)
    _say("Second factor removed and admin sessions ended; it can enrol again after signing in.")
    return 0


async def _apply(db: AsyncSession, options: Options) -> int:
    user = await auth_service.find_by_email(db, options.email)
    if user is None:
        return _refuse("No account has this address.")
    handlers = {
        Change.GRANT: _grant,
        Change.REVOKE: _revoke,
        Change.RESET_TWO_FACTOR: _reset_two_factor,
    }
    code = await handlers[options.change](db, user)
    await db.commit()
    return code


async def execute(
    options: Options, session_factory: async_sessionmaker[AsyncSession] | None = None
) -> int:
    """
    Apply the change `options` describes; return the exit code.

    Without a `session_factory` the application's own engine is used and closed
    when the change is done.
    """
    try:
        factory = session_factory or get_sessionmaker()
    except ConfigError as error:
        return _refuse(str(error))
    try:
        async with factory() as db:
            return await _apply(db, options)
    except (SQLAlchemyError, OSError) as error:
        return _refuse(
            f"Cannot reach the database ({type(error).__name__}). Is it migrated? Run `make migrate`."
        )
    finally:
        if session_factory is None:
            await dispose_engine()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command; return the process exit code."""
    return asyncio.run(execute(_parse_arguments(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
