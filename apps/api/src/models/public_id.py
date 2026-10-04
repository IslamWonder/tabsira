"""
Public ids: 64-bit, time-ordered and hard to count, the scheme Mastodon uses.

Every record whose id reaches a URL or an API response (a post, a comment, an
insight, a map entry) takes its primary key from `app.timestamp_id(table)`: the
creation time in milliseconds shifted left 16 bits, ORed with 16 bits from a
per-table sequence offset by a salted hash of the table and the millisecond.
Ids sort by creation time, need no coordination between workers, and do not
reveal how many rows a table holds the way a plain sequence would.

The salt is drawn at random when the function is created and lives only in the
database, so the offset cannot be computed from this public repository. A public
id is not a secret: sessions, consent ids and guest keys stay random tokens.

JSON carries public ids as strings (`src.schemas.public_id`): they exceed the
2^53 integers JavaScript can hold exactly.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Iterable
from typing import Any

from sqlalchemy import BigInteger, Connection, Table, event, text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import APP_SCHEMA, Base

TIMESTAMP_ID_FUNCTION = f"{APP_SCHEMA}.timestamp_id"
# Marks a column whose default is `timestamp_id`, so its sequence is created with the table.
PUBLIC_ID_INFO = "public_id"
_SALT_PATTERN = re.compile(r"[0-9a-f]{32}")
_TABLE_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,55}")


def new_salt() -> str:
    """Return 128 random bits as hex, the secret part of the function body."""
    return secrets.token_hex(16)


def timestamp_id_function_sql(salt: str) -> str:
    """Return the statement that creates `app.timestamp_id(table_name)` with `salt`."""
    if not _SALT_PATTERN.fullmatch(salt):
        message = "the salt must be 32 lower-case hex characters"
        raise ValueError(message)
    return f"""
        CREATE OR REPLACE FUNCTION {TIMESTAMP_ID_FUNCTION}(table_name text)
        RETURNS bigint
        LANGUAGE plpgsql VOLATILE AS $$
        DECLARE
            time_part bigint;
            sequence_base bigint;
            tail bigint;
        BEGIN
            time_part := ((date_part('epoch', clock_timestamp()) * 1000)::bigint) << 16;
            sequence_base := (
                'x' || substr(md5(table_name || '{salt}' || time_part::text), 1, 4)
            )::bit(16)::bigint;
            tail := (
                sequence_base + nextval(('{APP_SCHEMA}.' || table_name || '_id_seq')::regclass)
            ) & 65535;
            RETURN time_part | tail;
        END
        $$
    """


def sequence_name(table: str) -> str:
    """Return the qualified name of the sequence `timestamp_id(table)` reads."""
    if not _TABLE_PATTERN.fullmatch(table):
        message = f"not a table name: {table!r}"
        raise ValueError(message)
    return f"{APP_SCHEMA}.{table}_id_seq"


def create_sequence_sql(table: str) -> str:
    """Return the statement that creates the id sequence of `table`."""
    return f"CREATE SEQUENCE IF NOT EXISTS {sequence_name(table)}"


def public_id_pk(table: str) -> Mapped[int]:
    """Return a BIGINT primary key filled by `app.timestamp_id(table)`."""
    sequence_name(table)  # refuses a name that could not be a sequence's
    return mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
        # The cast is how PostgreSQL stores the default, so `alembic check` finds no difference.
        server_default=text(f"{TIMESTAMP_ID_FUNCTION}('{table}'::text)"),
        info={PUBLIC_ID_INFO: True},
    )


def create_public_id_objects(connection: Connection, tables: Iterable[Table]) -> None:
    """Create the id function and the sequence of every table among `tables` that needs one."""
    connection.execute(text(timestamp_id_function_sql(new_salt())))
    for table in tables:
        if any(column.info.get(PUBLIC_ID_INFO) for column in table.columns):
            connection.execute(text(create_sequence_sql(table.name)))


def _before_create(_target: Any, connection: Connection, **kwargs: Any) -> None:
    # A schema built from the models (tests, a fresh development database) needs the
    # function and the sequences before the first table names them in a default.
    create_public_id_objects(connection, kwargs.get("tables") or ())


event.listen(Base.metadata, "before_create", _before_create)
