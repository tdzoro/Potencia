"""revision labels

A label lets one resume carry several named versions ("Backend", "Data
engineer") without duplicating the uploaded document.

Revision ID: 0004_revision_labels
Revises: 0003_idempotency_keys
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004_revision_labels"
down_revision: str | None = "0003_idempotency_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("resume_revisions", sa.Column("label", sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column("resume_revisions", "label")
