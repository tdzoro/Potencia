"""Idempotency records for create endpoints (docs/API.md §1.5).

A double-submit on a slow connection must not create two analyses, two uploads
or two exports. The key is client-supplied, scoped to one account, and remembered
for 24 hours together with the response that was actually returned.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, JSON, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class IdempotencyKey(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "idempotency_keys"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(200), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    __table_args__ = (
        # The database, not the application, is what makes a replay race safe:
        # two concurrent requests with one key cannot both insert.
        UniqueConstraint("user_id", "key", name="uq_idempotency_keys_user_key"),
        Index("ix_idempotency_keys_created", "created_at"),
    )
