"""enable_extensions

Revision ID: 20261004_090100
Revises:
Create Date: 2026-10-04 09:01:00.000000

Creates every PostgreSQL extension the product uses. The provisioning scripts
install their packages on each host; this migration creates them in the
database. It never skips one: an extension that is not available makes the
migration fail, and the failure names it.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261004_090100"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# What each one is for.
EXTENSIONS = (
    "postgis",  # places, distances and bounding boxes
    "pg_trgm",  # fuzzy text search
    "unaccent",  # accent-insensitive text search
    "pgcrypto",  # hashing and random bytes in SQL
    "btree_gin",  # composite GIN indexes
    "btree_gist",  # exclusion constraints and composite GiST indexes
    "pg_stat_statements",  # query statistics
    "vector",  # pgvector: embeddings and similarity search
    "timescaledb",  # hypertables for the append-only time series
)


def upgrade() -> None:
    # Always in schema public: the role's search_path starts with `app`, and an
    # extension created without a schema would land in the first one of them.
    for extension in EXTENSIONS:
        op.execute(f'CREATE EXTENSION IF NOT EXISTS "{extension}" WITH SCHEMA public')


def downgrade() -> None:
    # Extensions are database-wide infrastructure, shared with the geodata chain
    # and with data that depends on their types. Removing them is a manual act.
    pass
