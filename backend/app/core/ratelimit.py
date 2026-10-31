"""Per-identity rate limiting (docs/API.md §4).

The limits are enforced with a sliding window held in process memory. That is
honest for a single-worker deployment and deliberately *not* silent about its
own limits: with more than one worker each process keeps its own counters, so a
shared store (Redis) becomes mandatory before scaling out. SECURITY.md says so.

The identity is the authenticated user when there is one, otherwise the client
IP. IP alone is a poor identity behind NAT, which is why an authenticated
request is counted against the account instead.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from app.core.logging import get_request_id

WINDOW_SECONDS = 3600


@dataclass(frozen=True)
class Limit:
    limit: int
    window_seconds: int = WINDOW_SECONDS


# Ordered most specific first: the first rule whose method and prefix match wins.
_RULES: tuple[tuple[str, str, Limit], ...] = (
    ("POST", "/api/v1/auth/login", Limit(5, 900)),
    ("POST", "/api/v1/auth/register", Limit(5, 900)),
    ("POST", "/api/v1/resumes", Limit(10)),
    ("POST", "/api/v1/analyses", Limit(20)),
    ("POST", "/api/v1/matches", Limit(20)),
    ("POST", "/api/v1/exports", Limit(30)),
    ("", "/api/v1/", Limit(300)),
)


def limit_for(method: str, path: str) -> Limit | None:
    for rule_method, prefix, limit in _RULES:
        if path.startswith(prefix) and (rule_method == "" or rule_method == method.upper()):
            return limit
    return None


def _identity(request: Request) -> str:
    """The account when the request carries a valid token, else the client IP.

    Counting an authenticated request against the account means a shared office
    IP does not throttle an entire building, and a single client rotating tokens
    cannot escape its own limit.
    """
    authorization = request.headers.get("authorization", "")
    token = authorization[7:] if authorization.lower().startswith("bearer ") else ""
    if token:
        try:
            from app.core.security import decode_token

            payload = decode_token(token)
            subject = payload.get("sub")
            if isinstance(subject, str) and subject:
                return f"user:{subject}"
        except Exception:  # noqa: BLE001 - an invalid token is simply not an identity
            pass
    return f"ip:{_client_ip(request)}"


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # The first entry is the original client; proxies append to the right.
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Counts hits per (identity, rule) and returns `429` with `Retry-After`."""

    def __init__(self, app, *, enabled: bool = True) -> None:
        super().__init__(app)
        self.enabled = enabled
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def reset(self) -> None:
        self._hits.clear()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self.enabled:
            return await call_next(request)

        limit = limit_for(request.method, request.url.path)
        if limit is None:
            return await call_next(request)

        key = (_identity(request), f"{request.method} {request.url.path}")
        now = time.monotonic()
        window = self._hits[key]

        while window and now - window[0] > limit.window_seconds:
            window.popleft()

        if len(window) >= limit.limit:
            retry_after = max(1, int(limit.window_seconds - (now - window[0])))
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_after)},
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests. Try again later.",
                        "details": [
                            {
                                "field": "request",
                                "issue": "rate_limited",
                                "meta": {"limit": limit.limit, "window_seconds": limit.window_seconds},
                            }
                        ],
                        "request_id": get_request_id(),
                    }
                },
            )

        window.append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit.limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit.limit - len(window)))
        return response
