"""Schemas for the health endpoint (docs/API.md §3.1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DependencyState = Literal["ok", "unavailable"]
HealthState = Literal["ok", "degraded"]


class Dependencies(BaseModel):
    database: DependencyState


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)
    request_id: str


class HealthResponse(BaseModel):
    """Present in both the healthy and degraded cases.

    The degraded case additionally carries `error`, so a monitor can read the
    standard envelope code (`dependency_unavailable`) while a human-facing
    client still gets the plain `status` / `dependencies` shape.
    """

    status: HealthState
    version: str
    environment: str
    dependencies: Dependencies
    uptime_seconds: int
    error: ErrorDetail | None = None
