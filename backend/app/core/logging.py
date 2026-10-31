"""Structured JSON logging with request correlation.

A resume is personal data. Request bodies, extracted text, filenames and tokens
must never reach a log line, so the request id is the only identifier an
operator needs to correlate a user-reported failure with server history.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

# Propagates the correlation id to whatever logs during request handling.
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_EXTRA_FIELDS = ("method", "path", "status", "duration_ms", "user_id")


class JsonFormatter(logging.Formatter):
    """One JSON object per line, so logs are machine-readable without a shipper."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def get_request_id() -> str:
    return request_id_ctx.get()


def set_request_id(value: str) -> contextvars.Token[str]:
    return request_id_ctx.set(value)


def configure_logging(level: str) -> None:
    """Install the JSON formatter on the root logger and on uvicorn's loggers."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    try:
        root.setLevel(level.upper())
    except ValueError:
        root.setLevel(logging.INFO)

    # uvicorn installs its own handlers that would emit plain text and bypass
    # the formatter; clear them so every line in the stream is JSON.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
