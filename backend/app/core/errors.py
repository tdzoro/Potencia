"""The single error envelope for every failure (docs/API.md §1.4).

One shape means the frontend has exactly one error path to implement, and a
`request_id` in every response means a user can report a failure without us
needing to log the document that caused it.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_request_id

logger = logging.getLogger(__name__)

# Documented codes only. Unknown statuses fall back to the closest documented
# meaning rather than inventing a new code the client has never seen.
_STATUS_TO_CODE: dict[int, str] = {
    400: "validation_error",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    405: "method_not_allowed",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    502: "dependency_unavailable",
    503: "dependency_unavailable",
}


def code_for_status(status_code: int) -> str:
    """Map a status to a documented code.

    405 in particular must not be reported as `validation_error`: a client that
    trusts the code would retry a request that can never succeed.
    """
    if status_code in _STATUS_TO_CODE:
        return _STATUS_TO_CODE[status_code]
    return "validation_error" if status_code < 500 else "internal_error"


class PotenciaError(Exception):
    """Raised by application code for a failure that is expected and documented."""

    def __init__(
        self,
        code: str,
        status_code: int,
        message: str,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.message = message
        self.details = details or []


def error_body(
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
            "request_id": request_id or get_request_id(),
        }
    }


def error_response(
    code: str,
    message: str,
    status_code: int,
    details: list[dict[str, Any]] | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_body(code, message, details, request_id),
        headers={"X-Request-ID": request_id or get_request_id()},
    )


def _request_id(request: Request) -> str:
    """Prefer the id stashed on the request: it survives middleware ordering."""
    return getattr(request.state, "request_id", None) or get_request_id()


def _validation_details(exc: RequestValidationError) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for error in exc.errors():
        loc = [str(part) for part in error.get("loc", ())][1:]  # drop "body"/"query"
        details.append(
            {
                "field": ".".join(loc) or None,
                "issue": error.get("type", "invalid"),
                "meta": {"message": error.get("msg", "")},
            }
        )
    return details


def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers so no failure escapes as a framework-shaped response."""

    @app.exception_handler(PotenciaError)
    async def _handle_potencia_error(request: Request, exc: PotenciaError) -> JSONResponse:
        logger.warning(
            "handled application error",
            extra={"path": request.url.path, "status": exc.status_code},
        )
        return error_response(exc.code, exc.message, exc.status_code, exc.details, _request_id(request))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            "validation_error",
            "The request body or parameters are invalid.",
            422,
            _validation_details(exc),
            _request_id(request),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = code_for_status(exc.status_code)
        message = exc.detail if isinstance(exc.detail, str) and exc.detail else "Request failed."
        return error_response(code, message, exc.status_code, None, _request_id(request))

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Logged in full server-side; the client receives nothing that could
        # expose internals such as SQL, filesystem paths or provider payloads.
        logger.exception(
            "unhandled exception",
            extra={"path": request.url.path, "status": 500},
        )
        return error_response(
            "internal_error",
            "An unexpected error occurred. The issue has been logged.",
            500,
            None,
            _request_id(request),
        )
