"""Test configuration.

The environment is set *before* the application is imported because settings are
cached on first access; a later assignment would silently have no effect.
"""

from __future__ import annotations

import os

os.environ.setdefault("POTENCIA_ENVIRONMENT", "test")
os.environ.setdefault(
    "POTENCIA_DATABASE_URL",
    "postgresql+psycopg://potencia:potencia@localhost:5432/potencia",
)
os.environ.setdefault("POTENCIA_SECRET_KEY", "test-secret-not-for-production")
os.environ.setdefault("POTENCIA_CORS_ORIGINS", "http://localhost:5173")

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client
