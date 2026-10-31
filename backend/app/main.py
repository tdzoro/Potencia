"""Application factory and ASGI entry point (`app.main:app`)."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes import health
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, set_request_id

logger = logging.getLogger(__name__)

# Inbound ids are accepted only if they look like one of ours; anything else is
# replaced, so a client cannot inject arbitrary text into headers and logs.
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

_ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
_ALLOWED_HEADERS = ["Authorization", "Content-Type", "X-Request-ID", "X-Idempotency-Key"]
_EXPOSED_HEADERS = ["X-Request-ID"]


def _resolve_request_id(request: Request) -> str:
    candidate = request.headers.get("X-Request-ID", "")
    return candidate if _REQUEST_ID_PATTERN.match(candidate) else f"req_{uuid4().hex[:20]}"


async def request_context(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Correlate every log line and response for one request."""
    request_id = _resolve_request_id(request)
    set_request_id(request_id)
    request.state.request_id = request_id

    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request failed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": 500,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        raise

    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request completed",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
    return response


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI application. Accepting settings keeps tests hermetic."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    if settings.is_production and settings.uses_insecure_secret:
        raise RuntimeError("POTENCIA_SECRET_KEY must be set when POTENCIA_ENVIRONMENT=production")

    docs_enabled = not settings.is_production
    app = FastAPI(
        title="POTENCIA API",
        version=settings.app_version,
        description="AI Resume Intelligence API",
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    # Credentials are in play, so origins are an explicit allow-list: a wildcard
    # with allow_credentials is both invalid and unsafe.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=_ALLOWED_METHODS,
        allow_headers=_ALLOWED_HEADERS,
        expose_headers=_EXPOSED_HEADERS,
        max_age=600,
    )
    app.middleware("http")(request_context)

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
