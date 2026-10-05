"""add_map_entry_sponsorship

Revision ID: 20261005_170000
Revises: 20261005_160000
Create Date: 2026-10-05 12:00:00.000000

«كفالة بصيرة» (decision 60). `map_entries` gains the `orphaned` state, `last_active_at` (the last
sign of life; every existing entry starts at the time of this migration, so the quiet period
begins at the deploy and nothing is orphaned retroactively) and `widened_level` (set once the
public place was widened, never cleared). `map_entry_generalisations` records each widening with
the earlier public point, cell and label, which no route reads. `map_entry_retired_ids` keeps the
public ids a widened entry had before it was given a new one. `map_entry_sponsorships` holds who
looks after an entry, one row per entry, and exists only while the sponsorship does. The
foreign keys to `map_entries` cascade updates, since widening gives the entry a new id. The
reports and the moderation log can name a sponsor's reflection. Written by hand after the models.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from src.models.public_id import create_sequence_sql, sequence_name

revision: str = "20261005_170000"
down_revision: str | Sequence[str] | None = "20261005_160000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"
STATUS_BEFORE = ("draft", "published", "pending_review", "removed", "withdrawn")
STATUS_AFTER = (*STATUS_BEFORE, "orphaned")
LEVELS = ("grid", "city", "region", "country")
REFLECTION_STATES = ("pending_review", "published", "rejected", "removed")
TARGETS_BEFORE = ("post", "comment", "map_entry")
TARGETS_AFTER = (*TARGETS_BEFORE, "sponsorship")
TARGET_TABLES = ("reports", "moderation_actions")
ACTIONS_BEFORE = ("published", "held", "rejected", "removed", "restored", "withdrawn")
ACTIONS_AFTER = (*ACTIONS_BEFORE, "superseded")
SOURCES_BEFORE = ("guard", "moderator", "reports", "owner")
SOURCES_AFTER = (*SOURCES_BEFORE, "job")


def _listed(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _one_of(table: str, column: str, values: tuple[str, ...]) -> sa.CheckConstraint:
    return sa.CheckConstraint(f"{column} IN ({_listed(values)})", name=op.f(f"ck_{table}_{column}"))


def _set_check(table: str, column: str, values: tuple[str, ...]) -> None:
    name = op.f(f"ck_{table}_{column}")
    op.drop_constraint(name, table, schema=SCHEMA, type_="check")
    op.create_check_constraint(name, table, f"{column} IN ({_listed(values)})", schema=SCHEMA)


def _entry_fk(table: str, cascade_update: bool) -> None:
    """Recreate the foreign key of `table.entry_id`, with or without cascading updates."""
    name = op.f(f"fk_{table}_entry_id_map_entries")
    op.drop_constraint(name, table, schema=SCHEMA, type_="foreignkey")
    op.create_foreign_key(
        name,
        table,
        "map_entries",
        ["entry_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="CASCADE",
        onupdate="CASCADE" if cascade_update else None,
    )


def upgrade() -> None:
    _set_check("map_entries", "status", STATUS_AFTER)
    op.add_column(
        "map_entries",
        sa.Column(
            "last_active_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "map_entries",
        sa.Column("widened_level", sa.String(length=32), nullable=True),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        op.f("ck_map_entries_widened_level"),
        "map_entries",
        f"widened_level IN ({_listed(LEVELS)})",
        schema=SCHEMA,
    )
    op.create_index(
        "ix_map_entries_orphaned_geom",
        "map_entries",
        ["public_geom"],
        schema=SCHEMA,
        postgresql_using="gist",
        postgresql_where=sa.text("status = 'orphaned'"),
    )
    op.create_index(
        "ix_map_entries_last_active",
        "map_entries",
        ["last_active_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("status = 'published'"),
    )
    _entry_fk("map_capture_points", cascade_update=True)

    op.create_table(
        "map_entry_retired_ids",
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column(
            "retired_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_map_entry_retired_ids")),
        schema=SCHEMA,
    )

    op.create_table(
        "map_entry_generalisations",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("entry_id", sa.BigInteger(), nullable=False),
        sa.Column("previous_cell_m", sa.Integer(), nullable=False),
        sa.Column("previous_public_lat", sa.Float(), nullable=True),
        sa.Column("previous_public_lng", sa.Float(), nullable=True),
        sa.Column("previous_place_label", sa.String(length=200), nullable=True),
        sa.Column("new_level", sa.String(length=32), nullable=False),
        sa.Column("new_label", sa.String(length=200), nullable=True),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        _one_of("map_entry_generalisations", "new_level", LEVELS),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["app.map_entries.id"],
            name=op.f("fk_map_entry_generalisations_entry_id_map_entries"),
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_map_entry_generalisations")),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_map_entry_generalisations_entry_id",
        "map_entry_generalisations",
        ["entry_id"],
        schema=SCHEMA,
    )

    op.execute(create_sequence_sql("map_entry_sponsorships"))
    op.create_table(
        "map_entry_sponsorships",
        sa.Column(
            "id",
            sa.BigInteger(),
            server_default=sa.text("app.timestamp_id('map_entry_sponsorships'::text)"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("entry_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("reflection", sa.String(length=500), nullable=True),
        sa.Column("reflection_status", sa.String(length=32), nullable=True),
        sa.Column("reflection_reason", sa.String(length=64), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(reflection IS NULL) = (reflection_status IS NULL)",
            name=op.f("ck_map_entry_sponsorships_reflection_has_state"),
        ),
        _one_of("map_entry_sponsorships", "reflection_status", REFLECTION_STATES),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["app.map_entries.id"],
            name=op.f("fk_map_entry_sponsorships_entry_id_map_entries"),
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.id"],
            name=op.f("fk_map_entry_sponsorships_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_map_entry_sponsorships")),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_map_entry_sponsorships_entry_id",
        "map_entry_sponsorships",
        ["entry_id"],
        unique=True,
        schema=SCHEMA,
    )
    op.create_index(
        "ix_map_entry_sponsorships_user_id",
        "map_entry_sponsorships",
        ["user_id", sa.text("started_at DESC")],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_map_entry_sponsorships_pending_review",
        "map_entry_sponsorships",
        ["started_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("reflection_status = 'pending_review'"),
    )
    for table in TARGET_TABLES:
        _set_check(table, "target_type", TARGETS_AFTER)
    _set_check("moderation_actions", "action", ACTIONS_AFTER)
    _set_check("moderation_actions", "source", SOURCES_AFTER)


def downgrade() -> None:
    op.execute(f"DELETE FROM {SCHEMA}.reports WHERE target_type = 'sponsorship'")
    op.execute(f"DELETE FROM {SCHEMA}.moderation_actions WHERE target_type = 'sponsorship'")
    op.execute(
        f"DELETE FROM {SCHEMA}.moderation_actions WHERE action = 'superseded' OR source = 'job'"
    )
    _set_check("moderation_actions", "action", ACTIONS_BEFORE)
    _set_check("moderation_actions", "source", SOURCES_BEFORE)
    for table in TARGET_TABLES:
        _set_check(table, "target_type", TARGETS_BEFORE)
    op.drop_table("map_entry_sponsorships", schema=SCHEMA)
    op.execute(f"DROP SEQUENCE IF EXISTS {sequence_name('map_entry_sponsorships')}")
    op.drop_table("map_entry_generalisations", schema=SCHEMA)
    op.drop_table("map_entry_retired_ids", schema=SCHEMA)
    # An anonymous entry must not come back with its author's name: it is withdrawn, with the
    # exact point it had, as its author would have withdrawn it.
    widened = "widened_level IS NOT NULL OR status = 'orphaned'"
    op.execute(
        f"DELETE FROM {SCHEMA}.map_capture_points WHERE entry_id IN "
        f"(SELECT id FROM {SCHEMA}.map_entries WHERE {widened})"
    )
    op.execute(
        f"UPDATE {SCHEMA}.map_entries SET status = 'withdrawn', withdrawn_at = now(), "
        "public_lat = NULL, public_lng = NULL, public_geom = NULL, place_geoname_id = NULL, "
        "place_label = NULL, admin_label = NULL, country_iso2 = NULL, country_label = NULL, "
        f"with_photo = false WHERE {widened}"
    )
    _entry_fk("map_capture_points", cascade_update=False)
    op.drop_index("ix_map_entries_last_active", table_name="map_entries", schema=SCHEMA)
    op.drop_index("ix_map_entries_orphaned_geom", table_name="map_entries", schema=SCHEMA)
    op.drop_constraint(
        op.f("ck_map_entries_widened_level"), "map_entries", schema=SCHEMA, type_="check"
    )
    op.drop_column("map_entries", "widened_level", schema=SCHEMA)
    op.drop_column("map_entries", "last_active_at", schema=SCHEMA)
    _set_check("map_entries", "status", STATUS_BEFORE)
