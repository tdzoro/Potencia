"""Retention sweep.

Exports carry an expiry; this removes the stored files and the rows once that
expiry passes, so a user's rendered documents do not outlive their usefulness.

Run it from cron or a scheduler:

    python -m app.tasks.retention
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.storage import get_store
from app.models.analysis import Export

logger = logging.getLogger(__name__)


def purge_expired_exports(now: datetime | None = None) -> int:
    """Delete expired export files and rows. Returns how many were removed."""
    moment = now or datetime.now(timezone.utc)
    store = get_store()
    removed = 0

    with get_sessionmaker()() as session:
        rows = list(
            session.scalars(select(Export).where(Export.expires_at.is_not(None), Export.expires_at < moment))
        )
        for row in rows:
            if row.storage_key:
                store.delete(row.storage_key)
            session.delete(row)
            removed += 1
        session.commit()

    if removed:
        logger.info("retention sweep removed expired exports", extra={"removed": removed})
    return removed


if __name__ == "__main__":  # pragma: no cover - operational entry point
    logging.basicConfig(level=logging.INFO)
    print(f"removed {purge_expired_exports()} expired export(s)")
