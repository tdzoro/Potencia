"""System health endpoint (unversioned, per docs/API.md §3.1)."""

from __future__ import annotations

import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core import database
from app.core.config import get_settings
from app.core.errors import error_body
from app.schemas.health import HealthResponse

router = APIRouter(tags=["system"])

# Monotonic, so a system clock correction cannot produce a negative uptime.
_PROCESS_START = time.monotonic()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness and dependency status",
    responses={503: {"model": HealthResponse, "description": "A required dependency is unreachable"}},
)
def read_health() -> JSONResponse:
    """Report liveness plus the state of required dependencies.

    Returns 200 only when every dependency is reachable; otherwise 503 while
    still serving, so the outage is observable from outside.

    Note: `docs/API.md` §1.4 asks every non-2xx response to use the error
    envelope, while §3.1 requires this body to keep `status` and `dependencies`
    at the top level. Both are honoured: the health fields stay where §3.1 puts
    them and the documented `dependency_unavailable` envelope is nested under
    `error`, so the response satisfies either reading.
    """
    settings = get_settings()
    database_state = database.check_database()
    healthy = database_state == "ok"

    body: dict[str, object] = {
        "status": "ok" if healthy else "degraded",
        "version": settings.app_version,
        "environment": settings.environment,
        "dependencies": {"database": database_state},
        "uptime_seconds": int(time.monotonic() - _PROCESS_START),
    }
    if not healthy:
        body["error"] = error_body(
            "dependency_unavailable",
            "The database is not reachable.",
            [{"dependency": "database"}],
        )["error"]

    return JSONResponse(status_code=200 if healthy else 503, content=body)
