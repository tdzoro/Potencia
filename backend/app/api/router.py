"""Aggregate router mounted at `/api/v1`.

Routers are added here as each phase lands them. Everything mounted here is
reachable under the versioned prefix, so a future `/v2` can be added without
moving existing clients.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import analyses, auth, jobs, matches, resumes

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(auth.users_router)
api_router.include_router(resumes.router)
api_router.include_router(analyses.router)
api_router.include_router(jobs.router)
api_router.include_router(matches.router)
