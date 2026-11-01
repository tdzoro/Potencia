"""export revision

An export can now render a chosen named version instead of always the newest,
and the record has to say which one it rendered. Nullable: every export created
before this migration rendered whatever was newest at the time.

Revision ID: 0005_export_revision
Revises: 0004_revision_labels
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005_export_revision"
down_revision: str | None = "0004_revision_labels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exports", sa.Column("revision_id", sa.Uuid(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_exports_revision_id_resume_revisions",
        "exports",
        "resume_revisions",
        ["revision_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_exports_revision_id_resume_revisions", "exports", type_="foreignkey")
    op.drop_column("exports", "revision_id")
