"""create_world_reveals

Revision ID: 20261005_100000
Revises: 20261004_209000
Create Date: 2026-10-05 10:00:00.000000

The world picture (decision 59): `world_reveals`, one row per owner and learned
concept, the circle of `data/world/layout-<version>.json` that concept lifted from
the clouds. A concept is revealed once per owner (`uq_*_concept`), a slot of a
region's layout is given once (`uq_*_slot`), and an insight makes at most one
reveal. No rows are written here: what was learned before this revision is
revealed from the completed insights the first time its owner's world loads
(`world_service.ensure_reveals`), which can run again safely. Written by hand
after the model.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from src.models.public_id import create_sequence_sql, sequence_name

revision: str = "20261005_100000"
down_revision: str | Sequence[str] | None = "20261004_209000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"
TABLE = "world_reveals"
THEMES = ("water", "planting", "knowledge", "patience", "kinship", "justice")
OWNERS = (("user", "user_id"), ("guest", "guest_key"))


def upgrade() -> None:
    op.execute(create_sequence_sql(TABLE))
    themes = ", ".join(f"'{theme}'" for theme in THEMES)
    op.create_table(
        TABLE,
        sa.Column(
            "id",
            sa.BigInteger(),
            server_default=sa.text(f"app.timestamp_id('{TABLE}'::text)"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("guest_key", sa.String(length=64), nullable=True),
        sa.Column("insight_id", sa.BigInteger(), nullable=False),
        sa.Column("place_id", sa.BigInteger(), nullable=False),
        sa.Column("concept_key", sa.String(length=64), nullable=False),
        sa.Column("region_id", sa.String(length=16), nullable=False),
        sa.Column("layout_version", sa.String(length=16), nullable=False),
        sa.Column("slot", sa.SmallInteger(), nullable=False),
        sa.Column("theme", sa.String(length=32), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("radius", sa.Float(), nullable=False),
        sa.Column("learned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("shown_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "num_nonnulls(user_id, guest_key) = 1", name=op.f("ck_world_reveals_one_owner")
        ),
        sa.CheckConstraint(
            "x >= 0 AND x <= 1 AND y >= 0 AND y <= 1", name=op.f("ck_world_reveals_on_the_picture")
        ),
        sa.CheckConstraint(
            "radius > 0 AND radius <= 0.25", name=op.f("ck_world_reveals_radius_bounded")
        ),
        sa.CheckConstraint("slot >= 0", name=op.f("ck_world_reveals_slot_not_negative")),
        sa.CheckConstraint(f"theme IN ({themes})", name=op.f("ck_world_reveals_theme")),
        sa.ForeignKeyConstraint(
            ["guest_key"],
            ["app.guests.key"],
            name=op.f("fk_world_reveals_guest_key_guests"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.id"],
            name=op.f("fk_world_reveals_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["insight_id"],
            ["app.insights.id"],
            name=op.f("fk_world_reveals_insight_id_insights"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["place_id"],
            ["app.world_places.id"],
            name=op.f("fk_world_reveals_place_id_world_places"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_world_reveals")),
        sa.UniqueConstraint("insight_id", name="uq_world_reveals_insight_id"),
        schema=SCHEMA,
    )
    for owner, column in OWNERS:
        where = sa.text(f"{column} IS NOT NULL")
        op.create_index(
            f"uq_world_reveals_{owner}_concept",
            TABLE,
            [column, "concept_key"],
            unique=True,
            schema=SCHEMA,
            postgresql_where=where,
        )
        op.create_index(
            f"uq_world_reveals_{owner}_slot",
            TABLE,
            [column, "layout_version", "region_id", "slot"],
            unique=True,
            schema=SCHEMA,
            postgresql_where=where,
        )
    op.create_index("ix_world_reveals_place_id", TABLE, ["place_id"], unique=False, schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_world_reveals_place_id", table_name=TABLE, schema=SCHEMA)
    for owner, column in OWNERS:
        where = sa.text(f"{column} IS NOT NULL")
        op.drop_index(
            f"uq_world_reveals_{owner}_slot",
            table_name=TABLE,
            schema=SCHEMA,
            postgresql_where=where,
        )
        op.drop_index(
            f"uq_world_reveals_{owner}_concept",
            table_name=TABLE,
            schema=SCHEMA,
            postgresql_where=where,
        )
    op.drop_table(TABLE, schema=SCHEMA)
    op.execute(f"DROP SEQUENCE IF EXISTS {sequence_name(TABLE)}")
