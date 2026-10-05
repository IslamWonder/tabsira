"""replace_likes_with_reactions

Revision ID: 20261005_160000
Revises: 20261005_150000
Create Date: 2026-10-05 11:00:00.000000

Reactions with a meaning (decision 61): `post_reactions` takes one row per account, post and
kind (`benefited` «انتفعتُ بها», `jazak` «جزاك الله خيرًا»), and replaces `post_likes`. Every
existing like becomes a `benefited` reaction with its own time, then `post_likes` is dropped.
The downgrade turns the `benefited` rows back into likes and loses the `jazak` ones, which a
like cannot hold. Written by hand after the model.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261005_160000"
down_revision: str | Sequence[str] | None = "20261005_150000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"
KINDS = ("benefited", "jazak")


def _created_at() -> sa.Column[sa.DateTime]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    kinds = ", ".join(f"'{kind}'" for kind in KINDS)
    op.create_table(
        "post_reactions",
        sa.Column("post_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        _created_at(),
        sa.CheckConstraint(f"kind IN ({kinds})", name=op.f("ck_post_reactions_kind")),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["app.posts.id"],
            name=op.f("fk_post_reactions_post_id_posts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.id"],
            name=op.f("fk_post_reactions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("post_id", "user_id", "kind", name="pk_post_reactions"),
        schema=SCHEMA,
    )
    op.create_index("ix_post_reactions_user_id", "post_reactions", ["user_id"], schema=SCHEMA)
    op.execute(
        "INSERT INTO app.post_reactions (post_id, user_id, kind, created_at) "
        "SELECT post_id, user_id, 'benefited', created_at FROM app.post_likes"
    )
    op.drop_table("post_likes", schema=SCHEMA)


def downgrade() -> None:
    op.create_table(
        "post_likes",
        sa.Column("post_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["app.posts.id"],
            name=op.f("fk_post_likes_post_id_posts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.id"],
            name=op.f("fk_post_likes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("post_id", "user_id", name="pk_post_likes"),
        schema=SCHEMA,
    )
    op.create_index("ix_post_likes_user_id", "post_likes", ["user_id"], schema=SCHEMA)
    op.execute(
        "INSERT INTO app.post_likes (post_id, user_id, created_at) "
        "SELECT post_id, user_id, created_at FROM app.post_reactions WHERE kind = 'benefited'"
    )
    op.drop_table("post_reactions", schema=SCHEMA)
