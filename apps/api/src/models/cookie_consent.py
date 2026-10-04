"""
Proof of cookie consent (decision 32): what a visitor chose, for which version of the policy, and when.

Distinct from `consents`, which records what a signed-in account agreed to (the terms,
keeping photos, personalisation, memory). This table is for the choice about cookies
and analytics, which anyone makes on their first visit, signed in or not.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DDL, Boolean, CheckConstraint, ForeignKey, Index, String, Uuid, event, true
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, created_at_column, uuid_pk
from src.user_agent import FAMILIES

_FAMILIES_SQL = "user_agent_family IN (" + ", ".join(f"'{name}'" for name in sorted(FAMILIES)) + ")"


class CookieConsent(Base):
    """
    One choice a visitor made, in one browser, at one time.

    `consent_id` is the anonymous id of the browser: random, made by the server and kept
    by the browser in a first-party cookie; every choice of that browser shares it. A new
    choice is a new row, and the latest row of an id is the choice in force. No IP address
    is kept, and the user agent only as a family (`src/user_agent.py`); the database
    refuses anything else. `user_id` is set when the visitor was signed in, so the choice
    can be shown in their profile and leaves with their account.

    Rows are only ever inserted: a trigger (below) refuses an update, a truncate and a
    delete, except the delete that removes the rows of a user who has just been deleted.
    """

    __tablename__ = "cookie_consents"
    __table_args__ = (
        # What the visitor cannot turn off: the cookies that keep a session and its security.
        CheckConstraint("necessary", name="necessary_always_on"),
        CheckConstraint(_FAMILIES_SQL, name="user_agent_family_known"),
        Index("ix_cookie_consents_consent_id_created_at", "consent_id", "created_at"),
        Index("ix_cookie_consents_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    consent_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    policy_version: Mapped[str] = mapped_column(String(32))
    necessary: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    analytics: Mapped[bool] = mapped_column(Boolean)
    behaviour: Mapped[bool] = mapped_column(Boolean)
    user_agent_family: Mapped[str] = mapped_column(String(32))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = created_at_column()


# The same statements are written out in the migration that creates the table; this copy
# builds the guard when a test schema is created from the models. The delete passes only
# when the row's user no longer exists, which is the state of a delete cascading from the
# user's own deletion; an anonymous row has no such user and never goes.
GUARD_FUNCTION = """
CREATE OR REPLACE FUNCTION app.cookie_consents_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.user_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM app.users WHERE id = OLD.user_id) THEN
            RETURN OLD;
        END IF;
    END IF;
    RAISE EXCEPTION 'cookie_consents is append-only: % refused', TG_OP
        USING ERRCODE = 'integrity_constraint_violation';
END
$$
"""
GUARD_TRIGGERS = (
    """
    CREATE TRIGGER cookie_consents_row_guard BEFORE UPDATE OR DELETE ON app.cookie_consents
    FOR EACH ROW EXECUTE FUNCTION app.cookie_consents_guard()
    """,
    """
    CREATE TRIGGER cookie_consents_truncate_guard BEFORE TRUNCATE ON app.cookie_consents
    FOR EACH STATEMENT EXECUTE FUNCTION app.cookie_consents_guard()
    """,
)

# SQLAlchemy ships DDL without type hints. DDL formats its statement with %, so the
# function's own % is doubled; the migration runs the text as it is.
for _statement in (GUARD_FUNCTION.replace("%", "%%"), *GUARD_TRIGGERS):
    _ddl = DDL(_statement)  # type: ignore[no-untyped-call]
    event.listen(CookieConsent.__table__, "after_create", _ddl.execute_if(dialect="postgresql"))
