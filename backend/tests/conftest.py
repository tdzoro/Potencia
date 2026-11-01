"""Test configuration.

Two things matter here:

1. The environment is set *before* the application is imported, because settings
   are cached on first access and a later assignment would silently do nothing.
2. Tests run against an in-memory SQLite database, so the suite needs no
   PostgreSQL and cannot touch a real one. The real schema is still exercised —
   `Base.metadata` is the same object Alembic reads.
"""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault("POTENCIA_ENVIRONMENT", "test")
# Uploads must land in a throwaway directory, never in the repository.
os.environ.setdefault(
    "POTENCIA_STORAGE_ROOT", tempfile.mkdtemp(prefix="potencia-test-storage-")
)
os.environ.setdefault(
    "POTENCIA_DATABASE_URL",
    "sqlite+pysqlite:///:memory:",
)
# 32+ bytes: shorter HMAC keys are flagged by the JWT library for good reason.
os.environ.setdefault(
    "POTENCIA_SECRET_KEY", "test-secret-not-for-production-0123456789abc"
)
os.environ.setdefault("POTENCIA_CORS_ORIGINS", "http://localhost:5173")
# By default tests run without Gemini API key so NullRewriteProvider is tested
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("POTENCIA_GEMINI_API_KEY", None)

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.database import get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture()
def engine() -> Iterator[Engine]:
    """A fresh in-memory database per test, so no test can see another's rows."""
    test_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite ignores foreign keys unless asked. PostgreSQL always enforces them,
    # so without this the tests would pass while cascade deletes silently failed
    # in production.
    @event.listens_for(test_engine, "connect")
    def _enforce_foreign_keys(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(test_engine)
    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(test_engine)
        test_engine.dispose()


@pytest.fixture()
def session(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db_session:
        yield db_session


@pytest.fixture()
def app(engine: Engine) -> FastAPI:
    """The real application, with only its database dependency redirected."""
    application = create_app()
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db() -> Iterator[Session]:
        db_session = factory()
        try:
            yield db_session
        finally:
            db_session.close()

    application.dependency_overrides[get_db] = override_get_db
    return application


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
