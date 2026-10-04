"""create_admin_access_tables

Revision ID: 20261004_150000
Revises: 20261004_140000
Create Date: 2026-10-04 15:00:00.000000

The admin area's sessions and the second factor of each admin. Both belong to a
user and go with the account (ON DELETE CASCADE).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261004_150000"
down_revision: str | Sequence[str] | None = "20261004_140000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"


def upgrade() -> None:
    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32", name=op.f("ck_admin_sessions_token_hash_length")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.id"],
            name=op.f("fk_admin_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_admin_sessions_token_hash")),
        schema=SCHEMA,
    )
    op.create_index("ix_admin_sessions_user_id", "admin_sessions", ["user_id"], schema=SCHEMA)
    op.create_index("ix_admin_sessions_expires_at", "admin_sessions", ["expires_at"], schema=SCHEMA)
    op.create_table(
        "admin_totp",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        # A Fernet token: the shared secret, encrypted. Never the secret itself.
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        # Keyed hashes of the recovery codes; a spent code is removed from the list.
        sa.Column(
            "recovery_hashes",
            postgresql.ARRAY(sa.String(length=64)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_step", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.id"],
            name=op.f("fk_admin_totp_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_admin_totp")),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("admin_totp", schema=SCHEMA)
    op.drop_table("admin_sessions", schema=SCHEMA)
