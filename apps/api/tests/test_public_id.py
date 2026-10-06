from __future__ import annotations

import time

import pytest
from pydantic import BaseModel, ValidationError
from sqlalchemy import BigInteger, Column, MetaData, Table, text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.models import public_id_pk
from src.models.public_id import (
    PUBLIC_ID_INFO,
    create_public_id_objects,
    create_sequence_sql,
    new_salt,
    sequence_name,
    timestamp_id_function_sql,
)
from src.schemas.public_id import MAX_PUBLIC_ID, PublicId, parse_public_id


class Item(BaseModel):
    id: PublicId


# ─── The JSON form ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("given", "expected"), [("1", 1), (42, 42), (str(MAX_PUBLIC_ID), MAX_PUBLIC_ID)]
)
def test_a_public_id_is_read_from_a_string_or_a_number(given, expected):
    assert parse_public_id(given) == expected


@pytest.mark.parametrize(
    "bad", [True, "0", "-1", "01", "1e3", " 1", "abc", 0, -5, MAX_PUBLIC_ID + 1, 1.5]
)
def test_anything_else_is_refused(bad):
    with pytest.raises(ValueError, match="public id"):
        parse_public_id(bad)


def test_json_carries_the_id_as_a_string_and_python_keeps_the_number():
    item = Item(id="114564384939048960")

    assert item.model_dump() == {"id": 114564384939048960}
    assert item.model_dump_json() == '{"id":"114564384939048960"}'
    with pytest.raises(ValidationError):
        Item(id="not-a-number")


def test_the_schema_tells_the_web_client_it_is_a_string():
    for mode in ("validation", "serialization"):
        schema = Item.model_json_schema(mode=mode)["properties"]["id"]

        assert schema["type"] == "string"
        assert schema["pattern"] == "^[1-9][0-9]{0,18}$"


# ─── Names, salt and the column ────────────────────────────────────


def test_the_salt_is_random_hex_and_a_bad_one_is_refused():
    first, second = new_salt(), new_salt()
    assert first != second
    assert len(first) == 32
    assert "app.timestamp_id(table_name text)" in timestamp_id_function_sql(new_salt())
    with pytest.raises(ValueError, match="32 lower-case hex"):
        timestamp_id_function_sql("'; DROP TABLE app.users; --")


def test_a_sequence_belongs_to_a_plain_table_name():
    assert sequence_name("posts") == "app.posts_id_seq"
    assert create_sequence_sql("posts") == "CREATE SEQUENCE IF NOT EXISTS app.posts_id_seq"
    for bad in ("Posts", "posts; drop", "", "1posts"):
        with pytest.raises(ValueError, match="not a table name"):
            sequence_name(bad)
    with pytest.raises(ValueError, match="not a table name"):
        public_id_pk("bad name")


def test_the_column_is_a_bigint_key_the_function_fills_and_marks_for_its_sequence():
    column = public_id_pk("posts").column

    assert isinstance(column.type, BigInteger)
    assert column.primary_key is True
    assert column.autoincrement is False
    assert str(column.server_default.arg) == "app.timestamp_id('posts'::text)"
    assert column.info == {PUBLIC_ID_INFO: True}


# ─── In the database ───────────────────────────────────────────────


async def test_the_models_schema_already_holds_the_function(engine: AsyncEngine):
    async with engine.connect() as connection:
        found = await connection.scalar(text("SELECT to_regproc('app.timestamp_id') IS NOT NULL"))

    assert found is True


async def test_ids_are_time_ordered_unique_and_start_at_the_current_millisecond(
    engine: AsyncEngine,
):
    metadata = MetaData(schema="app")
    probe = Table(
        "public_id_probes",
        metadata,
        Column(
            "id",
            BigInteger,
            primary_key=True,
            server_default=text("app.timestamp_id('public_id_probes')"),
            info={PUBLIC_ID_INFO: True},
        ),
    )
    plain = Table(
        "public_id_plain_probes",
        metadata,
        Column("id", BigInteger, primary_key=True, autoincrement=False),
    )
    before = int(time.time() * 1000)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda sync: create_public_id_objects(sync, [probe, plain]))
            await connection.run_sync(metadata.create_all)
            ids = [
                await connection.scalar(
                    text("INSERT INTO app.public_id_probes DEFAULT VALUES RETURNING id")
                )
                for _ in range(50)
            ]
            plain_sequence = await connection.scalar(
                text("SELECT to_regclass('app.public_id_plain_probes_id_seq')")
            )
        after = int(time.time() * 1000)

        assert len(set(ids)) == 50
        assert ids == sorted(ids)
        assert all(before - 5 <= value >> 16 <= after + 5 for value in ids)
        assert all(0 < value <= MAX_PUBLIC_ID for value in ids)
        # A table with no public id gets no sequence.
        assert plain_sequence is None
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(metadata.drop_all)
            await connection.execute(text("DROP SEQUENCE IF EXISTS app.public_id_probes_id_seq"))
