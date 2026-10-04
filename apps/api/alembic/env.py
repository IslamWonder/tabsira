"""Alembic environment of the `app` chain: every table of the application."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from typing import Any

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from src.config import get_settings
from src.models import Base

APP_SCHEMA = "app"

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ConfigParser treats % as interpolation, and a password may contain one.
config.set_main_option(
    "sqlalchemy.url", get_settings().database_url.get_secret_value().replace("%", "%%")
)

target_metadata = Base.metadata


def include_name(name: str | None, type_: str, parent_names: Any) -> bool:
    """
    Look only at the `app` schema when comparing models with the database.

    The geodata schema belongs to the other chain (alembic_geodata), and the
    default schema holds what the extensions installed (PostGIS tables, for one),
    which no model describes and no autogenerate run should propose to drop.
    """
    if type_ == "schema":
        return name == APP_SCHEMA
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
        version_table_schema=APP_SCHEMA,
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
        version_table_schema=APP_SCHEMA,
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
        # The role's search_path starts with `app`, which made `app` the default
        # schema: autogenerate then skipped it and saw no table, so `alembic
        # check` passed while the models and the database disagreed. With the
        # extensions' schema as the default, `app` is a named schema like any other.
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
