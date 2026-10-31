"""Database engine and session lifecycle.

The engine is built lazily and `create_engine` never opens a connection, so the
API boots and reports `degraded` when PostgreSQL is unreachable instead of
failing to start. A health probe that cannot report a database outage because
the process died is useless.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,  # recycles connections dropped by a restart or failover
        future=True,
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session that is always closed."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def check_database() -> str:
    """Return `"ok"` or `"unavailable"`; never raises into the caller."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok"
    except Exception:  # driver, DNS, auth and timeout failures all mean the same thing here
        logger.warning("database health check failed", exc_info=True)
        return "unavailable"
