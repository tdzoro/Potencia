"""idempotency keys

Client-supplied `X-Idempotency-Key` values are stored with the response they
produced, so a retried create returns the original result instead of doing the
work twice.

Revision ID: 0003_idempotency_keys
Revises: 0002_recommendation_remediation
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003_idempotency_keys"
down_revision: str | None = "0002_recommendation_remediation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("path", sa.String(length=200), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_idempotency_keys_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_keys")),
        sa.UniqueConstraint("user_id", "key", name="uq_idempotency_keys_user_key"),
    )
    op.create_index("ix_idempotency_keys_created", "idempotency_keys", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_created", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
