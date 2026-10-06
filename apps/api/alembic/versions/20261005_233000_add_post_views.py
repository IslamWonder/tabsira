"""add_post_views

Revision ID: 20261005_233000
Revises: 20261005_200000
Create Date: 2026-10-05 23:30:00.000000

`posts.views_count` counts the views of a post: once per viewer a day, never the author's, never a
bot's (`src/services/view_service.py`). It is a counter, unlike everything else of the social
network, because a view leaves no row: who saw a post is never kept. Zero for every post that
exists. Written by hand after the model.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261005_233000"
down_revision: str | Sequence[str] | None = "20261005_200000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"


def upgrade() -> None:
    op.add_column(
        "posts",
        sa.Column("views_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        op.f("ck_posts_views_count_not_negative"), "posts", "views_count >= 0", schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_posts_views_count_not_negative"), "posts", schema=SCHEMA, type_="check"
    )
    op.drop_column("posts", "views_count", schema=SCHEMA)
