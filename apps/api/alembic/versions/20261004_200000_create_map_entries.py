"""create_map_entries

Revision ID: 20261004_200000
Revises: 20261004_192700
Create Date: 2026-10-04 20:00:00.000000

«أطلس بصائر العالم» (extension §10): `map_entries`, the public side of a placed insight (the
approximation cell's centre as a PostGIS point, the cell size, the GeoNames label, the state),
and `map_capture_points`, the private side (the exact point, read by its owner alone), in two
tables so no public query can touch the private one. Reports and the moderation log may now
name a map entry. Written by hand after the models.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from geoalchemy2 import Geometry

from alembic import op
from src.models.public_id import create_sequence_sql, sequence_name

revision: str = "20261004_200000"
down_revision: str | Sequence[str] | None = "20261004_192700"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"
REPORT_TARGETS_BEFORE = "target_type IN ('post', 'comment')"
REPORT_TARGETS_AFTER = "target_type IN ('post', 'comment', 'map_entry')"
TARGET_TABLES = ("reports", "moderation_actions")


def _one_of(table: str, column: str, values: tuple[str, ...]) -> sa.CheckConstraint:
    listed = ", ".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} IN ({listed})", name=op.f(f"ck_{table}_{column}"))


def upgrade() -> None:
    op.execute(create_sequence_sql("map_entries"))
    op.create_table(
        "map_entries",
        sa.Column(
            "id",
            sa.BigInteger(),
            server_default=sa.text("app.timestamp_id('map_entries'::text)"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("insight_id", sa.BigInteger(), nullable=False),
        sa.Column("public_lat", sa.Float(), nullable=True),
        sa.Column("public_lng", sa.Float(), nullable=True),
        sa.Column("public_geom", Geometry("POINT", srid=4326, spatial_index=False), nullable=True),
        sa.Column("cell_m", sa.Integer(), nullable=False),
        sa.Column("location_meaning", sa.String(length=32), nullable=False),
        sa.Column("place_geoname_id", sa.BigInteger(), nullable=True),
        sa.Column("place_label", sa.String(length=200), nullable=True),
        sa.Column("admin_label", sa.String(length=200), nullable=True),
        sa.Column("country_iso2", sa.String(length=2), nullable=True),
        sa.Column("country_label", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column("status_reason", sa.String(length=64), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL",
            name=op.f("ck_map_entries_published_has_time"),
        ),
        sa.CheckConstraint(
            "status <> 'published' OR (public_lat IS NOT NULL AND public_lng IS NOT NULL)",
            name=op.f("ck_map_entries_published_has_point"),
        ),
        _one_of("map_entries", "location_meaning", ("capture_point", "public_place")),
        _one_of(
            "map_entries",
            "status",
            ("draft", "published", "pending_review", "removed", "withdrawn"),
        ),
        sa.ForeignKeyConstraint(
            ["insight_id"],
            ["app.insights.id"],
            name=op.f("fk_map_entries_insight_id_insights"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.id"],
            name=op.f("fk_map_entries_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_map_entries")),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_map_entries_live_insight",
        "map_entries",
        ["insight_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("status <> 'withdrawn'"),
    )
    op.create_index(
        "ix_map_entries_pending_review",
        "map_entries",
        ["created_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("status = 'pending_review'"),
    )
    op.create_index(
        "ix_map_entries_public_geom",
        "map_entries",
        ["public_geom"],
        schema=SCHEMA,
        postgresql_using="gist",
        postgresql_where=sa.text("status = 'published'"),
    )
    op.create_index(
        "ix_map_entries_published",
        "map_entries",
        [sa.text("published_at DESC"), sa.text("id DESC")],
        schema=SCHEMA,
        postgresql_where=sa.text("status = 'published'"),
    )
    op.create_index(
        "ix_map_entries_place",
        "map_entries",
        ["place_geoname_id"],
        schema=SCHEMA,
        postgresql_where=sa.text("status = 'published'"),
    )
    op.create_index("ix_map_entries_user_id", "map_entries", ["user_id"], schema=SCHEMA)
    op.create_table(
        "map_capture_points",
        sa.Column("entry_id", sa.BigInteger(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("accuracy_m", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "latitude BETWEEN -90 AND 90", name=op.f("ck_map_capture_points_latitude_range")
        ),
        sa.CheckConstraint(
            "longitude BETWEEN -180 AND 180", name=op.f("ck_map_capture_points_longitude_range")
        ),
        sa.CheckConstraint(
            "accuracy_m IS NULL OR accuracy_m >= 0",
            name=op.f("ck_map_capture_points_accuracy_positive"),
        ),
        _one_of("map_capture_points", "source", ("device_capture", "photo_exif", "user_selected")),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["app.map_entries.id"],
            name=op.f("fk_map_capture_points_entry_id_map_entries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("entry_id", name=op.f("pk_map_capture_points")),
        schema=SCHEMA,
    )
    for table in TARGET_TABLES:
        op.drop_constraint(op.f(f"ck_{table}_target_type"), table, schema=SCHEMA, type_="check")
        op.create_check_constraint(
            op.f(f"ck_{table}_target_type"), table, REPORT_TARGETS_AFTER, schema=SCHEMA
        )


def downgrade() -> None:
    op.execute(f"DELETE FROM {SCHEMA}.reports WHERE target_type = 'map_entry'")
    op.execute(f"DELETE FROM {SCHEMA}.moderation_actions WHERE target_type = 'map_entry'")
    for table in TARGET_TABLES:
        op.drop_constraint(op.f(f"ck_{table}_target_type"), table, schema=SCHEMA, type_="check")
        op.create_check_constraint(
            op.f(f"ck_{table}_target_type"), table, REPORT_TARGETS_BEFORE, schema=SCHEMA
        )
    op.drop_table("map_capture_points", schema=SCHEMA)
    op.drop_index("ix_map_entries_pending_review", table_name="map_entries", schema=SCHEMA)
    op.drop_index("uq_map_entries_live_insight", table_name="map_entries", schema=SCHEMA)
    op.drop_index("ix_map_entries_user_id", table_name="map_entries", schema=SCHEMA)
    op.drop_index("ix_map_entries_place", table_name="map_entries", schema=SCHEMA)
    op.drop_index("ix_map_entries_published", table_name="map_entries", schema=SCHEMA)
    op.drop_index("ix_map_entries_public_geom", table_name="map_entries", schema=SCHEMA)
    op.drop_table("map_entries", schema=SCHEMA)
    op.execute(f"DROP SEQUENCE IF EXISTS {sequence_name('map_entries')}")
