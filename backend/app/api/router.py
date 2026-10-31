"""Aggregate router mounted at `/api/v1`.

Routers are added here as each phase lands them (auth in Phase 3, resumes and
analyses in Phase 4, matching in Phase 8, exports in Phase 12). It is
intentionally empty now: a mounted router with no implemented endpoints is the
only honest state at Phase 2.
"""

from __future__ import annotations

from fastapi import APIRouter

api_router = APIRouter()
