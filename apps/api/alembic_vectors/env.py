"""Alembic environment of the `vectors` chain: the scripture embeddings (decision 48)."""

from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path
from typing import Any

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# This chain is run with `-c alembic_vectors/alembic.ini`, so the application
# package is not on the path unless it is added here.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_settings
from src.models import VectorsBase

VECTORS_SCHEMA = "vectors"

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ConfigParser treats % as interpolation, and a password may contain one.
config.set_main_option(
    "sqlalchemy.url", get_settings().database_url.get_secret_value().replace("%", "%%")
)

target_metadata = VectorsBase.metadata


def include_name(name: str | None, type_: str, parent_names: Any) -> bool:
    """
    Look only at the `vectors` schema when comparing models with the database.

    Its tables hold keys to `app` tables; the app chain owns those, so they are
    known to the comparison through the keys and never created or dropped here.
    """
    if type_ == "schema":
        return name == VECTORS_SCHEMA
    return True


def run_migrations_offline() -> None:
    """Emit the migration SQL without connecting to the database."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        version_table_schema=VECTORS_SCHEMA,
        include_schemas=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        version_table_schema=VECTORS_SCHEMA,
        include_schemas=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        # As in the app chain: with the role's search_path (app, corpus, geodata, vectors)
        # the keys to `corpus` tables reflect without their schema and never match the
        # models. With the extensions' schema as the default, every schema is named.
        connect_args={"server_settings": {"search_path": "public"}},
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
