"""Delete generated export files once their retention window has passed.

`exports.expires_at` was recorded from the first version of the export feature
and the UI told users the file is removed after 24 hours, but nothing performed
the removal. A promise the product makes has to be kept by the product, so this
task does it.

Deletion is driven by the row, not by a directory walk: an export that has been
deleted by hand leaves nothing to find, and a file with no row was never
promised to anyone.

    python -m app.tasks.retention --once        # one pass, then exit
    python -m app.tasks.retention --interval 3600
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.storage import get_store
from app.models.analysis import Export

logger = logging.getLogger(__name__)


def purge_expired_exports(db: Session, *, now: datetime | None = None) -> int:
    """Remove expired exports and their bytes. Returns the number of rows removed."""
    cutoff = now or datetime.now(timezone.utc)
    records = list(
        db.scalars(
            select(Export).where(Export.expires_at.is_not(None), Export.expires_at < cutoff)
        )
    )

    store = get_store()
    for record in records:
        if record.storage_key:
            # A missing file is not an error: the row still has to go, otherwise
            # the metadata outlives the bytes it describes.
            store.delete(record.storage_key)
        db.delete(record)

    if records:
        db.commit()
    return len(records)


def run_once(factory: sessionmaker[Session]) -> int:
    with factory() as db:
        removed = purge_expired_exports(db)
    if removed:
        logger.info("retention purged exports", extra={"removed": removed})
    return removed


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Purge expired POTENCIA export files.")
    parser.add_argument("--once", action="store_true", help="run a single pass and exit")
    parser.add_argument("--interval", type=int, default=3600, help="seconds between passes")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    if args.once:
        removed = run_once(factory)
        print(f"purged {removed} expired export(s)")
        engine.dispose()
        return

    logger.info("retention scheduler started", extra={"interval_seconds": args.interval})
    try:
        while True:
            try:
                run_once(factory)
            except Exception:  # noqa: BLE001 - one failed pass must not stop the loop
                logger.exception("retention pass failed")
            time.sleep(args.interval)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
