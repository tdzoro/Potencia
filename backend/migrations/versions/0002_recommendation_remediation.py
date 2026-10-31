"""add recommendations.remediation

Every recommendation must carry a next step, not only a diagnosis. Existing rows
get an empty string so the column can be NOT NULL without a backfill guess.

Revision ID: 0002_recommendation_remediation
Revises: 39a2d441cff4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002_recommendation_remediation"
down_revision: str | None = "39a2d441cff4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recommendations",
        sa.Column("remediation", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("recommendations", "remediation")
