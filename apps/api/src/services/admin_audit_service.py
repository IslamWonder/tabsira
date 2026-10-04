"""
Writing the admin audit log.

The log records that an admin did something to a record, never what they wrote. The
function that builds a row's details takes only typed arguments (field names, a reason
code, record ids), so a value an admin typed has no way in; `details_of` refuses a field
name that is not an identifier, which is what a value would look like.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.admin_audit import AdminAuditLog, AuditAction

USER_AGENT_MAX = 256
# The columns' own lengths. A request can name any view or record in its address, so what
# is longer is cut here instead of failing the insert, which would turn a 404 into a 500.
MODEL_MAX = 64
RECORD_ID_MAX = 256
# A bulk action lists the records it touched, up to this many; the count is always exact.
MAX_LISTED_IDS = 50
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_REASON = re.compile(r"^[a-z0-9_]{1,64}$")


def details_of(
    *,
    fields: Iterable[str] = (),
    reason: str | None = None,
    ids: Iterable[str] = (),
) -> dict[str, Any] | None:
    """
    Build the details of one row, or None when there is nothing to say.

    `fields` are the names of the columns that changed, `reason` a short code
    (`bad_password`), `ids` the records an action touched. Anything else is refused.
    """
    details: dict[str, Any] = {}
    names = sorted(set(fields))
    if any(not _NAME.match(name) for name in names):
        message = "an audit field must be a column name"
        raise ValueError(message)
    if names:
        details["fields"] = names
    if reason is not None:
        if not _REASON.match(reason):
            message = "an audit reason must be a lower-case code"
            raise ValueError(message)
        details["reason"] = reason
    listed = [str(record_id)[:RECORD_ID_MAX] for record_id in ids]
    if listed:
        details["count"] = len(listed)
        details["ids"] = listed[:MAX_LISTED_IDS]
    return details or None


async def record(
    db: AsyncSession,
    *,
    action: AuditAction,
    admin_user_id: uuid.UUID | None = None,
    model: str | None = None,
    record_id: str | None = None,
    fields: Iterable[str] = (),
    reason: str | None = None,
    ids: Iterable[str] = (),
    ip_hash: str | None = None,
    user_agent: str | None = None,
) -> AdminAuditLog:
    """
    Add one row to the audit log and flush it; the caller commits.

    Commit even when the request goes on to be refused: a failed sign-in is exactly
    the row that must survive.
    """
    row = AdminAuditLog(
        action=action,
        admin_user_id=admin_user_id,
        model=(model or None) and model[:MODEL_MAX],
        record_id=(record_id or None) and record_id[:RECORD_ID_MAX],
        details=details_of(fields=fields, reason=reason, ids=ids),
        ip_hash=ip_hash,
        user_agent=(user_agent or None) and user_agent[:USER_AGENT_MAX],
    )
    db.add(row)
    await db.flush()
    return row
