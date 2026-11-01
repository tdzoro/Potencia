"""auth tokens

Reusable authentication token table for email verification and secure password recovery.
Stores cryptographically hashed tokens with expiration and single-use tracking.

Revision ID: 0006_auth_tokens
Revises: 0005_export_revision
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0006_auth_tokens"
down_revision: str | None = "0005_export_revision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("token_type", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_auth_tokens_user_id_users",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_auth_tokens_user_id", "auth_tokens", ["user_id"])
    op.create_index("ix_auth_tokens_token_hash", "auth_tokens", ["token_hash"], unique=True)
    op.create_index("ix_auth_tokens_token_type", "auth_tokens", ["token_type"])
    op.create_index("ix_auth_tokens_expires_at", "auth_tokens", ["expires_at"])
    op.create_index("ix_auth_tokens_used_at", "auth_tokens", ["used_at"])


def downgrade() -> None:
    op.drop_index("ix_auth_tokens_used_at", table_name="auth_tokens")
    op.drop_index("ix_auth_tokens_expires_at", table_name="auth_tokens")
    op.drop_index("ix_auth_tokens_token_type", table_name="auth_tokens")
    op.drop_index("ix_auth_tokens_token_hash", table_name="auth_tokens")
    op.drop_index("ix_auth_tokens_user_id", table_name="auth_tokens")
    op.drop_table("auth_tokens")

